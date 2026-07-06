#!/usr/bin/env python
# vim: noet ts=4 number
from monosim.constants import CURRENCY_SYMBOL, GO_AMOUNT
from monosim.board import game_board, get_community_chest_cards, get_chance_cards
from monosim.bank import Bank
from monosim.player import Player
from monosim.custom_exceptions import InsufficientFundsAvailable, CannotDoThat#, CommandIncomplete

import asyncio
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(filename='/var/log/archimede/MonopolyServer.log', level=logging.DEBUG)

from synaptism.protocol import writeX, recv

import traceback
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

	@property
	def _name(self):
		return f"{self.name} (caca)"

	async def broadcast(self, msg, NOT = ()):
		msg = msg.encode()
		for player in self.list_players:
			if player not in NOT:
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
			await self.broadcast( f"{self.name}: {player._name} has joined the game", NOT = (player, ) )

		for player in self.list_players:
			player.meet_other_players(self.list_players)
	
		await self.broadcast(f"{self.name}: game starts.")
		self.has_started = True

		try:
			while True:
				await self.broadcast("A new day has risen.")
				self.turn_count += 1

				for player in self.list_players:
					print(f"it's {player._name}'s turn")
					player_has_rolled_dice = False
					writeX(player.writer, f"{player._name}: it's your turn to play.".encode() )
					await player.writer.drain()
					current_rent_amount = self._game_board[player._position].estimate_rent(player)	# meeh.. can't we get rid of this call?
					cell = self._game_board[player._position]

					# reading input from *all* players
					while True:
						try:
							sender, dic = self.input_queue.get_nowait()
							cmd = dic['uuids'][1].split(b' ', 1)	# 'context'
						except asyncio.queues.QueueEmpty:
							await asyncio.sleep(1)
							continue

						try:
							if not any([c.startswith(cmd[0]) for c in (b'offer', b'bid', b'drop', b'take', b'give', \
									b'tell', b'shout', b'say', b'examine', b'x', b'score', b'look', b'manage', b'help')]):
								# these actions are reserved to the player whose turn it is

								if sender != player:
									writeX( sender.writer, b"Not your turn to play" )
									await sender.writer.drain()

								if b'pass'.startswith(cmd[0]) or (b'end'.startswith(cmd[0]) and b'turn'.startswith(cmd[1])):
									if not player_has_rolled_dice:
										writeX( sender.writer, b"You cannot end your turn just yet: need to roll the dice." )
									else:
										writeX( sender.writer, b"You end your turn." )
										break

								elif b'roll'.startswith(cmd[0]):
									cmd[0] = b'roll'
									if b'dice'.startswith(cmd[1]):
										if player_has_rolled_dice:
											writeX( player.writer, "You have already rolled your dice this turn.".encode('utf-8') )
											continue
										player_has_rolled_dice = True

										if not player.rent_paid and current_rent_amount:
											player._debts.append( cell.belongs_to, current_rent_amount)
											await self.broadcast(f"""{player._name} committed filouterie d'auberge! Total debt is now {sum([a for _, a in player._debts])}{CURRENCY_SYMBOL}""")
										tuple_dices = await player.roll_dice()
										player._dice_value = tuple_dices[0] + tuple_dices[1]

									elif b'over'.startswith(cmd[1]):
										await self.broadcast(f"""{player._name} lies flat on the ground and rolls over""")
									elif b'cigarette'.startswith(cmd[1]):
										await self.broadcast(f"""{player._name} rolls themselves a cigarette""")

									if player._game._game_board[player._position].type != 'jail' and not player._jail_count:
										cell, current_rent_amount = await player.advance(player._dice_value)
										player.rent_paid = False if current_rent_amount else True

									elif self._jail_count:
										current_rent_amount, player.rent_paid = 0, True	# NOTE it would make sense to set rent_paid to False
										writeX( player.writer, f"You are in jail with {player._jail_count} days left to rot here. Unless you want to pay?".encode('utf-8') )

									# TODO make this explicit.. with 'take'
									if len(cell.inventory):
										for item, amount in cell.inventory:
											# TODO only treat this as cash if it is cash!
											player._cash += amount
											await self.broadcast(f"{player._name} found {amount}{CURRENCY_SYMBOL} of {item}")
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
										writeX( player.writer, f"Tax was {cell.tax_amount}{CURRENCY_SYMBOL}, thank you and see you soon!".encode('utf-8') )

									elif cell.type == 'go to jail':
										await player.go_to_jail()

									elif cell.type == 'community chest':
										self.community_cards_deck.discard( await self.community_cards_deck.draw(player) )
										# just to be safe, doesn't hurt (whatever the card is)
										cell = self._game_board[player._position]
										current_rent_amount = cell.estimate_rent(player)

									elif cell.type == 'chance':
										self.chance_cards_deck.discard( await self.chance_cards_deck.draw(player) )
										# just to be safe, doesn't hurt (whatever the card is)
										cell = self._game_board[player._position]
										current_rent_amount = cell.estimate_rent(player)



								elif b'buy'.startswith(cmd[0]):
									cmd[0] = b'buy'
									if b'road'.startswith(cmd[1]):
										await player.buy_road( cell )
									elif b'property'.startswith(cmd[1]) or b'station'.startswith(cmd[1]) or b'utility'.startswith(cmd[1]) :
										await player.buy_property( cell )
										await self.broadcast(f"{player._name} is now the owner of {cell.name}")
									elif b'house'.startswith(cmd[1]):
										await player.buy_house( cell )
										await self.broadcast(f"{player._name} bought a house on {cell.name} ; rent is now {cell.estimate_rent(None)}{CURRENCY_SYMBOL}")
									elif b'hotel'.startswith(cmd[1]):
										await player.buy_hotel( cell )
										await self.broadcast(f"{player._name} bought a hotel on {cell.name} ; rent is now {cell.rent_with_4_houses_1_hotels}{CURRENCY_SYMBOL}")
									else:
										raise IndexError
									await sender.writer.drain()

								elif b'pay'.startswith(cmd[0]):
									cmd[0] = b'pay'
									if b'rent'.startswith(cmd[1]):
										if current_rent_amount:
											await player.pay_opponent( cell.belongs_to, current_rent_amount )
											await self.broadcast(f"{player._name} paid {current_rent_amount}{CURRENCY_SYMBOL} rent to {cell.belongs_to}")
											current_rent_amount = 0
										else:
											if cell.belongs_to is None:
												await lose_money(cell)
											else:
												await self.broadcast(f"{player._name} owned no rent to {cell.belongs_to} but paid anyway.")
												await player.pay_opponent( cell.belongs_to, current_rent_amount )
									elif b'bail'.startswith(cmd[1]):
										if cell.type == 'jail' and player._jail_count:
											if player.have_enough_money(50):
												await player.pay_bank(50)
												await player.get_out_of_jail()
											elif not await player.is_bankrupt(50):
												await player.get_money_from_mortgages(50)
												await player.pay_bank(50)
												await player.get_out_of_jail()
										else:
											lose_money(cell)

									else:
										writeX( player.writer, "Pay what?" )
										await player.writer.drain()

								else:
									writeX( player.writer, b"Not a valid command" )
									await player.writer.drain()
							else:
								# these actions are available to any player, anytime
								if not len(cmd[0]):
									pass

								elif b'score'.startswith(cmd[0]):
									writeX(sender.writer, sender.get_score(self.turn_count).encode() )

								elif b'look'.startswith(cmd[0]):
									writeX( sender.writer, cell.description.encode('utf-8') )

								elif b'examine'.startswith(cmd[0]) or b'x'.startswith(cmd[0]):
									cmd[0] = b'examine'
									what = cmd[1]
									if b'road'.startswith(what) or \
											b'property'.startswith(what) or \
											b'station'.startswith(what) or \
											b'utility'.startswith(what) or \
											b'cell'.startswith(what):
										writeX( sender.writer, self._game_board[sender._position].examine().encode('utf-8') )
									else:
										raise IndexError

								elif b'manage'.startswith(cmd[0]):
									for p, action in await player.choose_mortgage_properties( player.list_mortgageable_properties ):
										if action == 'mortgage':
											await self.mortgage(p)
										if action == 'unmortgage':
											await self.unmortgage(p)

								elif b'bid'.startswith(cmd[0]):
									cmd[0] = b'bid'
									try:
										try:
											prop_id = int(cmd[1])
										except ValueError:
											# TODO also accept integer string (cell name)
											writeX( sender.writer, f"Could not convert {cmd[1].decode('utf-8')} to a cell number".encode('utf-8'))
											continue
										except IndexError:
											# default to current cell
											prop_id = self._game_board.index(cell)
										prop = self._game_board[prop_id]
									except ValueError:
										continue
									except IndexError:
										writeX( sender.writer, f"{prop_id} is not a valid cell number".encode('utf-8'))
										continue
									else:
										# TODO prevent bidding if cell is not buyable
										await self.broadcast(f"{player._name} bids {cell.name} (NotImplementedError)")

								elif b'offer'.startswith(cmd[0]):
									cmd[0] = b'offer'
									try:
										amount = int(cmd[1])
									except ValueError:
										writeX( sender.writer, f"Could not convert {cmd[1].decode('utf-8')} to an integer amount".encode('utf-8'))
									else:
										await self.broadcast(f"{player._name} offers {amount}{CURRENCY_SYMBOL} for {cell.name} (NotImplementedError)")

								elif b'help'.startswith(cmd[0]):
									writeX( sender.writer, """Available commands:
    roll			[dice]
	end turn		end your turn
	pass			alias for 'end turn'
	score			check your score
	look			look around
	examine			<object|cell>
	x				alias for 'examine'
	buy				<road|station|utility>
	sell			<road|station|utility>		TODO
	give			<something> to <someone>	TODO
	drop			<something>					TODO
	take			<something>					TODO
	pay				<rent|bail>
	manage			manage property mortgaging
	bid				[property] (put property for auction)		TODO
	offer			<amount> (offer amount for current auction)	TODO
	say				<something>					TODO
	shout			<something>					TODO
	tell			<someone> <something>		TODO
	help			this message
	?				alias for 'help'
""")
						except (CannotDoThat, ) as e:
							writeX( sender.writer, str(e).encode('utf-8') )
						except IndexError as e:
							writeX( sender.writer, f"{cmd[0].decode('utf-8')} what? (failed to process command)".encode('utf-8') )


		except (InsufficientFundsAvailable, Exception) as e:
			traceback.print_exception(type(e), e, e.__traceback__)
			#raise
			#if input("play again? ").lower() in ('y','yes'):
			#	return True
			#return False


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
				player_name = res['uuids'][1]	# 'context'
				logger.info(f"{self.name}: {addr} connected ; their name is {player_name}")
				await asyncio.sleep(.1)	# lol!
				writeX(writer, f"Hello, {player_name.decode()}".encode('utf-8'))
				await writer.drain()
				self.players.append((player_name, reader, writer))

				if len(self.players) == self.player_count:
					task = asyncio.create_task(self.games[GAME_ID].game_loop( self.players ))

				# waiting for all players
				while not self.games[GAME_ID].has_started:
					await asyncio.sleep(1)

				player = self.games[GAME_ID]._dict_players[player_name]

				while True:
					cmd = await recv(reader)
					try:
						# interactive subroutine is active
						player._input_queue.put_nowait(cmd)
					except AttributeError:
						self.games[GAME_ID].input_queue.put_nowait(( player, cmd ))

		try:
			server = await asyncio.start_server(handle, self.host, self.port)

		except OSError as e:
			logger.fatal(f"could not start MonopolyServer {self.port=} ({e})")
			exit(1)

		else:
			addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
			logger.info(f"{self.name}: MonopolyServer starting {addrs}:{self.port=}")
			print(f"{self.name}: listening on {addrs}:{self.port=}")

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
