#!/usr/bin/env python
# vim: noet ts=4 number
from monosim.constants import CURRENCY_SYMBOL, GO_AMOUNT, DATETIME_FMT
from monosim.board import game_board, get_community_chest_cards, get_chance_cards
from monosim.bank import Bank
from monosim.player import Player as monoPlayer
from monosim.game import Game
from monosim.custom_exceptions import InsufficientFundsAvailable, CannotDoThat, AllDone
from monosim.art import welcome_screen, text_large, post_welcome, post_init

import asyncio
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(filename='/var/log/archimede/MonopolyServer.log', level=logging.DEBUG)

from synaptism.protocol import writeX, recv

import pendulum
import quart
import random

GAME_ID = 'mono'

class Player:
	def __init__(self, name, reader, writer):
		self._name = name
		#print(f"<<<<<<<<<<<<<<<< {self._name=}")
		self.reader, self.writer = reader, writer

		self._game = None
		self.is_ready = False

class MonopolyPlayer(monoPlayer, Player): pass


class MonopolyServer(quart.Quart):
	def __init__(self, host = '0.0.0.0', port = 9876, name = 'MonopolyServer', max_player_count = 21):
		super().__init__(name)
		self.name = name
		self.host, self.port = host, port 
		self.max_player_count, self.dict_players = max_player_count, {}
		self.startuptime = pendulum.now()
		self.games = {}
		self.list_players = []


	async def serve(self):
		""" telnet server """
		async def handle(reader, writer):
			addr = writer.get_extra_info('peername')

			if len(self.dict_players) == self.max_player_count:
				writeX(writer, b"You have been kicked (reason: server is full)")
				return

			#writeX(writer, welcome_screen)
			writeX(writer, text_large)
			writeX(writer, b"Enter your name:")
			await writer.drain()

			try:
				res = await recv( reader )
			except EOFError:
				logger.error("EOFError in stream")
			else:
				player_name = res['uuids'][1].decode('utf-8')	# 'context'

				try:
					for p in self.list_players:
						if p._name == player_name:
							raise KeyError
				except KeyError:
					print(f"Error: a player with this name already exists ({player_name})")
					return
				else:
					player = self.dict_players[player_name] = MonopolyPlayer( player_name, reader, writer)

				self.list_players.append(player)
				logger.info(f"{self.name}: {addr} connected ; their name is {player_name}")
				await asyncio.sleep(.1)	# lol!

				writeX(writer, f"Hello, {player_name}. The Guild of the Great Game Wizards welcomes you! ".encode('utf-8'))
				writeX(writer, post_welcome)
				await writer.drain()

				while True:
					while not player._game or not player._game.has_started:
						while not player._game:
							writeX(writer, "You are in the server lobby and have not joind any game yet.".encode('utf-8'))
							cmd = (await recv( reader ))['uuids'][1].split(b' ', 1)	# 'context'

							if b'join'.startswith(cmd[0]):
								game_name = cmd[1].decode('utf-8')
								try:
									player._game = self.games[game_name]
								except KeyError:
									writeX(writer, f"no game by the name '{game_name}' was found ; try 'list games'".encode('utf-8'))

							elif b'create'.startswith(cmd[0]):
								game_name = cmd[1].decode('utf-8')
								self.games[game_name] = Game(
									admin = player,
									board = game_board, bank = Bank(),
									community_cards_deck = get_community_chest_cards(),
									chance_cards_deck = get_chance_cards(),
									name = game_name)
								player._game = self.games[game_name]
								break
								
							elif b'list'.startswith(cmd[0]):
								if b'games'.startswith(cmd[1]):
									writeX(writer, f"Games on '{self.name}':".encode('utf-8'))
									for g in self.games.keys():
										writeX(writer, f"\t{g}".encode('utf-8'))
								elif b'players'.startswith(cmd[1]):
									writeX(writer, f"Players on '{self.name}':".encode('utf-8'))
									for p in self.dict_players.keys():
										writeX(writer, f"\t{p}".encode('utf-8'))

						writeX(writer, f"You have joined the game's lobby for '{player._game.name}'".encode('utf-8'))

						# waiting for all players to say 'ready' or for game to be explicitly started by the admin
						while not player._game.has_started:
							cmd = (await recv( reader ))['uuids'][1].split(b' ', 1)	# 'context'

							if not len(cmd[0]):
								continue
							elif any([c.startswith(cmd[0]) for c in (b'kick', b'start')]):
								# commands reserved to the game admin
								if player._game.game_admin != player:
									writeX( player.writer, b"You're not the admin of that game, so you cannot do that :-P" )
									await player.writer.drain()
								elif b'start'.startswith(cmd[0]):
									#print("trying to start", player._game.name)
									task = asyncio.create_task(self.games[player._game.name].game_loop( self.list_players ))
									await asyncio.sleep(1)	# waiting for the game to start..
									await player._game.broadcast( f"{player._name} (game admin) forced-started the game '{player._game.name}'. Enter any command to exit the game's lobby and start playing.", NOT=(player,) )	# TODO  meeh this is not cool, we want a timeout on recv()
								elif b'kick'.startswith(cmd[0]):
									raise NotImplementedError

							else:
								# commands for any players
								if b'ready'.startswith(cmd[0]):
									player.is_ready = True
									raise NotImplementedError
								elif b'leave'.startswith(cmd[0]):
									player._game = None
									break
								elif b'list'.startswith(cmd[0]):
									if b'players'.startswith(cmd[1]):
										writeX(writer, f"Players in game '{player._game.name}':".encode('utf-8'))
										for p in self.dict_players.values():
											if p._game == player._game:
												writeX(writer, f"\t{p._name}".encode('utf-8'))

					writeX(writer, f"You are now in the game '{player._game.name}' ; you will return to the main lobby once the game has ended.".encode('utf-8'))	# TODO can games actually end cleanly at this stage?

					# game loop
					while player._game.has_started:
						cmd = await recv(reader)
						try:
							# interactive subroutine is active
							player._input_queue.put_nowait(cmd)
						except AttributeError:
							# "normal" game command input
							player._game.input_queue.put_nowait(( player, cmd ))

		try:
			server = await asyncio.start_server(handle, self.host, self.port)

		except OSError as e:
			logger.fatal(f"could not start MonopolyServer {self.port=} ({e})")
			exit(1)

		else:
			addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
			logger.info(f"{self.name}: MonopolyServer starting {addrs}:{self.port=}")
			print(f"{self.name}: listening on {addrs}")#{', '.join(addrs[0])}:{addrs[1]}")

			try:
				async with server:
					await server.serve_forever()
			except Exception as e:
				self.logger.fatal(f"{self.name}: MonopolyServer crashed")
		finally:
			logger.info(f"{self.name}: MonopolyServer was shut down")


async def main(max_player_count):
	S = MonopolyServer(max_player_count = max_player_count)

	@S.route("/")
	async def home():
		import psutil
		return await quart.render_template('index.html',
				S=S, game=S.games[GAME_ID],
				DATETIME_FMT = DATETIME_FMT,
				ram = psutil.virtual_memory(),
				#disk_usage = usage = psutil.disk_usage(partition.mountpoint),
				disk_usage = psutil.disk_usage('/stor0/naspi/'),
				loadavg = tuple(round(l, 3) for l in psutil.getloadavg()),
			)

	telnet_task = asyncio.create_task( S.serve() )

	await S.run_task(
			host='0.0.0.0',
			port=5555,
			debug=True,
		)


if __name__ == '__main__':
	from sys import argv
	try:
		max_player_count = int(argv[1])
	except IndexError:
		max_player_count = 10
	

	asyncio.run(main(max_player_count))
