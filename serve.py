#!/usr/bin/env python
# vim: noet ts=4 number
from monosim.board import game_board, get_community_chest_cards, get_chance_cards
from monosim.bank import Bank
from monosim.player import Player
from monosim.custom_exceptions import InsufficientFundsAvailable, CannotDoThat

import asyncio
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(filename='/var/log/archimede/MonopolyServer.log', level=logging.DEBUG)

from synaptism.protocol import writeX, recv

from q import q

class Game:
	def __init__(self, board, bank, community_cards_deck, chance_cards_deck, name = 'Monopoly'):
		self.name = name
		self.list_players, self._dict_players = [], {}
		self._game_board, self.bank = board, bank
		self.community_cards_deck, self.chance_cards_deck = community_cards_deck, chance_cards_deck
		self.input_queue = asyncio.Queue()
		self.turn_count = 0
		self.has_started = False


	async def broadcast(self, msg, NOT = None):
		msg = msg.encode()
		for player in self.list_players:
			if player is not NOT:
				#print(f"\tBroadcasting: {msg} to {player}")
				writeX( player.writer, msg )
				await player.writer.drain()

	async def game_loop(self, players):
		for player_name, reader, writer in players:
			self.list_players.append(
					p := Player(player_name.decode('utf-8'), self, reader, writer),
				)
			try:
				self._dict_players[player_name]
			except KeyError:
				self._dict_players[player_name] = p
				print(f"{self._dict_players[player_name]}")
			else:
				print(f"Error: a player with this name already exists ({player_name})")
				self.list_players.pop()
				raise Exception(f"Error: a player with this name already exists ({player_name})")

		for player in self.list_players:
			await self.broadcast( f"{self.name}: {player._name} has joined the game", NOT = player )

		for player in self.list_players:
			player.meet_other_players(self.list_players)
	
		await self.broadcast(f"{self.name}: game starts.")
		self.has_started = True

		try:
			while True:
				await self.broadcast("A new day has risen.")
				self.turn_count += 1

				for player in self.list_players:
					#writeX(player.writer, player.get_print_state(self.turn_count).encode() )
					writeX(player.writer, f"{player._name}: it's your turn to play.".encode() )
					#await player.writer.drain()
					current_rent_amount = self._game_board[player._position].estimate_rent(player)	
					cell = self._game_board[player._position]

					# reading input from *all* players
					while True:
						#try:
						#if True:
							#print(f"attempting to read from self.input_queue")
						sender, dic = await self.input_queue.get()
						#except asyncio.queues.QueueEmpty:
						#	print(f"no read (QueueEmpty)")
						#	await asyncio.sleep(1)
						#else:
							#print(f"{player} {dic=}")
						cmd = dic['uuids'][1].split(b' ')
						print(f"{player} {cmd=}")
						try:
							if not any([c.startswith(cmd[0]) for c in (b'make_offer', b'bid')]):
								if sender != player:
									writeX( sender.writer, b"Not your turn to play" )
									sender.writer.drain()

								if b'pass'.startswith(cmd[0]):
									writeX( sender.writer, b"You end your turn" )
									break
								elif b'roll'.startswith(cmd[0]):
									if not player.rent_paid and current_rent_amount:
										player._debts.append( cell.belongs_to, current_rent_amount)
										await self.broadcast(f"""{player._name} committed filouterie d'auberge! Total debt is now {sum([a for _, a in player._debts])}""")

									tuple_dices = player.roll_dice()
									player._dice_value = tuple_dices[0] + tuple_dices[1]

									if player._game._game_board[player._position].type != 'jail' and not player._jail_count:
										player.advance(player._dice_value)
										cell = self._game_board[player._position]
										writeX( player.writer, cell.description.encode('utf-8') )
									elif self._jail_count:
										writeX( player.writer, f"You are in jail with {player._jail_count} days left to rot here. Unless you want to pay?".encode('utf-8') )


									current_rent_amount = self._game_board[player._position].estimate_rent(player)	
									player.rent_paid = False if current_rent_amount else True
									if current_rent_amount:
										await self.broadcast(f"{player._name} landed on {cell}, rent is {current_rent_amount} ; the weather is {random.choice(['great','so-so','bad','horrible'])}", NOT=player)
									else:
										await self.broadcast(f"{player._name} landed on {cell} ; the weather is {random.choice(['great','so-so','bad','horrible'])}", NOT=player)

									if len(cell.inventory):
										for item, amount in cell.inventory:
											player._cash += amount
											await self.broadcast(f"{player._name} found {amount} of {item}")
										cell.inventory.clear()

									# jail logic
									if cell.type == 'jail' and player._jail_count:
										player._jail_count -= 1

										# Double roll
										if tuple_dices[0] == tuple_dices[1]:
											player.get_out_of_jail()

										# Player has been 3 rounds in jail
										elif not player._jail_count:
											if player.have_enough_money(50):
												player.pay_bank(50)
												player.get_out_of_jail()
											else:
												if not await player.is_bankrupt(50):
													amount_to_mortgage = 50 - player._cash
													await player.get_money_from_mortgages(amount_to_mortgage)
													player.pay_bank(50)
													player.get_out_of_jail()

									elif cell.type == 'tax':
										await player.pay_tax(cell.tax_amount)
										writeX( player.writer, f"Tax was {cell.tax_amount}, thank you and see you soon!".encode('utf-8') )

									elif cell.type == 'go to jail':
										player.go_to_jail()

									elif cell.type == 'community chest':
										self.community_cards_deck.discard( self.community_cards_deck.draw(self) )

									elif cell.type == 'chance':
										self.chance_cards_deck.discard( self.chance_cards_deck.draw(self) )



								elif b'buy'.startswith(cmd[0]):
									if b'road'.startswith(cmd[1]):
										await player.buy_road( cell )
										await self.broadcast(f"{player._name} is now the owner of {cell.name} ; rent is now {cell.estimate_rent(None)}")
									elif b'property'.startswith(cmd[1]):
										await player.buy_property( cell )
										await self.broadcast(f"{player._name} is now the owner of {cell.name}")
									elif b'house'.startswith(cmd[1]):
										await player.buy_house( cell )
										await self.broadcast(f"{player._name} bought a house on {cell.name} ; rent is now {cell.estimate_rent(None)}")
									elif b'hotel'.startswith(cmd[1]):
										await player.buy_hotel( cell )
										await self.broadcast(f"{player._name} bought a hotel on {cell.name} ; rent is now {cell.rent_with_4_houses_1_hotels}")
								elif b'mortgage'.startswith(cmd[0]):
										player.mortgage( cell )
										await self.broadcast(f"{player._name} has mortgaged {cell.name}".format(player._name, cell.name))
								elif b'unmortgage'.startswith(cmd[0]):
										player.unmortgage( cell )
										await self.broadcast(f"{player._name} unmortgaged {cell.name}".format(player._name, cell.name))
								elif b'pay'.startswith(cmd[0]):
									if b'rent'.startswith(cmd[1]):
										if current_rent_amount:
											player.pay_opponent( cell.belongs_to, current_rent_amount )
											await self.broadcast(f"{player._name} paid {current_rent_amount} rent to {cell.belongs_to}")
											current_rent_amount = 0
										else:
											if cell.belongs_to is None:
												lose_money(cell)
											else:
												await self.broadcast(f"{player._name} owned no rent to {cell.belongs_to} but paid anyway.")
												player.pay_opponent( cell.belongs_to, current_rent_amount )
									elif b'bail'.startswith(cmd[1]):
										if cell.type == 'jail' and player._jail_count:
											if player.have_enough_money(50):
												player.pay_bank(50)
												player.get_out_of_jail()
											elif not await player.is_bankrupt(50):
												await player.get_money_from_mortgages(50)
												player.pay_bank(50)
												player.get_out_of_jail()
										else:
											lose_money(cell)

									else:
										writeX( player.writer, "Pay what?" )
										await player.writer.drain()
								elif b'choose'.startswith(cmd[0]):
									if b'mortgage'.startswith(cmd[1]):
										await player.choose_mortgage_properties( player.list_mortgageable_properties )
									elif b'unmortgage'.startswith(cmd[1]):
										await player.choose_unmortgage_properties()
								else:
									writeX( player.writer, b"Not a valid command" )
									await player.writer.drain()
							else:
								if b'bid'.startswith(cmd[0]):
									await self.broadcast(f"{player._name} bids {amount} on {cell.name} (NotImplementedError)")
								elif b'make_offer'.startswith(cmd[0]):
									await self.broadcast(f"{player._name} offers {amount} for {cell.name} (NotImplementedError)")
						except (CannotDoThat, ) as e:
							writeX( sender.writer, str(e).encode('utf-8') )

		except (InsufficientFundsAvailable, Exception) as e:
			print(">>>>", e)
			raise
			if input("play again? ").lower() in ('y','yes'):
				return True
			return False


import random

GAME_ID = 'Prout'

class MonopolyServer:
	def __init__(self, host = '0.0.0.0', port = 9876, name = 'MonopolyServer', player_count = 2):
		self.name = name
		self.host, self.port = host, port 
		self.player_count, self.players = player_count, []

		# setup game

		#for seed in range(0, 10000):
		seed = 1024
		random.seed(seed)
		self.games = {
			'Prout': Game( 
				game_board, Bank(),
				get_community_chest_cards(), get_chance_cards(),
				name = f"Monopoly{seed}"),
		}




	async def serve(self):
		""" telnet server """
		async def handle(reader, writer):
			addr = writer.get_extra_info('peername')
			
			writeX(writer, b"Enter your name:")
			await writer.drain()
			try:
				res = await recv( reader )
			except EOFError:
				logger.error("EOFError in stream")
			else:
				player_name = res['uuids'][1]
				logger.info(f"{self.name}: {addr} connected ; their name is {player_name}")
				await asyncio.sleep(.1)	# lol!
				writeX(writer, f"Hello, {player_name.decode()}".encode())
				await writer.drain()
				#q("handle()", res)
				self.players.append((player_name, reader, writer))

				if len(self.players) == self.player_count:
					task = asyncio.create_task(self.games[GAME_ID].game_loop( self.players ))
					#await self.games[GAME_ID].game_loop( self.players )



				# waiting for all players
				while not self.games[GAME_ID].has_started:
					#print(f"waiting for game to start ({player_name})")
					await asyncio.sleep(1)

				#print(f"starting game {player_name} {self.games[GAME_ID]._dict_players}")
				player = self.games[GAME_ID]._dict_players[player_name]

				while True:
					#print(f"waiting for cmd from {player_name}...")
					cmd = await recv(reader)
					#print(f"{player_name} sent {cmd}")
					self.games[GAME_ID].input_queue.put_nowait(( player, cmd ))
					#print(f"{player_name} added to queue")

		try:
			server = await asyncio.start_server(handle, self.host, self.port)

		except OSError as e:
			logger.fatal(f"could not start MonopolyServer {self.port=} ({e})")
			exit(1)

		else:
			addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
			logger.info(f"{self.name}: MonopolyServer starting {addrs}:{self.port=}")

			try:
				async with server:
					await server.serve_forever()
			except Exception as e:
				self.logger.fatal(f"{self.name}: MonopolyServer crashed")
		finally:
			logger.info(f"{self.name}: MonopolyServer was shut down")


if __name__ == '__main__':
	from sys import argv
	try:
		player_count = int(argv[1])
	except IndexError:
		player_count = 2
	
	s = MonopolyServer(player_count = player_count)
	asyncio.run(s.serve())
