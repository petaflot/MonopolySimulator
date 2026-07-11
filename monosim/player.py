# vim: noet ts=4 number
import asyncio
from monosim.board import get_color_to_house_mapping
from monosim.custom_exceptions import *
import random
from copy import copy
#  TODO allow user to set verbosity. Text should be printed only if verbosity=1 is set.
#   Add paramenter to the constructor and a ad-hoc function set_verbosity().
#   Do this first otherwise it's impossible to run the simulations with jupyter notebooks because of the excessive
#   amount of text in the output.
# TODO make test function to check if the _list_mortgaged_roads is properly used. DO not mortgage properties
#  from this list Check that attribute _properties_total_mortgageable_amount and _list_mortgaged_roads always sum up
#  to the same value
#  TODO Implement cards functionality (opportunity, etc.)
from termcolor import cprint

"""
	NOTE: for algorithmic simplicity, house count on a street stays at 4 if a hotel is built
"""

from monosim.constants import CURRENCY_SYMBOL, GO_AMOUNT, AMOUNT_WIDTH, format_amount
from monosim.dice import roll_dice_physical, roll_dice_auto
from monosim.board import get_color_to_house_mapping
color_to_house_mapping, color_property_count = get_color_to_house_mapping()

from synaptism.protocol import writeX

from q import q

COLOR_STR_LEN = 10

class Player:
	_dict_owned_colors = {color: None for color in color_to_house_mapping.keys()}

	def __init__(self, name, reader, writer, dice_func = None):
		#print(f">>>>>>>>>>>>>>>> {name=}")
		super().__init__( name, reader, writer )

		self._position = 0
		self._dice_value = 0
		self._cash = 1500
		self._properties_total_mortgageable_amount = 0
		self._player_cards = []
		self._debts = []
		self._list_owned_roads = []
		self._list_owned_stations = []
		self._list_owned_utilities = []
		self._list_mortgaged_roads = []
		self._list_mortgaged_stations = []
		self._list_mortgaged_utilities = []
		self._dict_owned_houses_hotels = {}
		self.inventory = ['iPhone']	# TODO buy from shop on 'Go'/'Free parking'
		self._jail_count = 0
		self._list_players = None
		self.rent_multiplicator = 1
		self.rent_to_pay = 0
		self._roll_dice = roll_dice_auto if dice_func is None else dice_func
		self._has_lost = False


	def roll_dice(self):
		return self._roll_dice(player = self, game = self._game)

	async def input(self, prompt):
		self._input_queue = asyncio.Queue()
		writeX(self.writer, prompt.encode('utf-8'))
		res = (await self._input_queue.get())['uuids'][1]	# 'context'
		delattr( self, '_input_queue')
		return res.decode('utf-8')

	def __str__(self):
		return f"<Player:{self._name}>"

	def __repr__(self):
		return f"<Player:{self._name}@{hex(id(self))}>"

	@property
	def owned_colors(self):
		return tuple([c for c, player in self._dict_owned_colors.items() if player is self])

	def get_state(self):
		""" Get the player's state. The state contains information such as position, roads owned, money, mortgaged
			properties, etc.

		:return: (dictionary) key: property, value: property value (e.g. {'cash': 100, 'position': 10, ...})
		"""
		return {'name': self._name, 'position': self._position,
				'dice_value': self._dice_value, 'cash': self._cash,
				'mortgageable_amount': self._properties_total_mortgageable_amount, 'jail_count': self._jail_count,
				'player_cards': self._player_cards, 'owned_roads': self._list_owned_roads,
				'owned_stations': self._list_owned_stations, 'owned_utilities': self._list_owned_utilities,
				'mortgaged_roads': self._list_mortgaged_roads, 'mortgaged_stations': self._list_mortgaged_stations,
				'mortgaged_utilities': self._list_mortgaged_utilities, 'owned_colors': self.owned_colors,
				'owned_houses_hotels': self._dict_owned_houses_hotels, 'has_lost': self._has_lost,
				'bank_cash': self._game.bank.cash}

	def get_score(self, turn_count):
		owned_hotels = sum([i[1] for i in self._dict_owned_houses_hotels.values()])

		def get_roads_owned():
			colors = []
			for color in self._dict_owned_colors.keys():
				color_roads = [road for road in self._list_owned_roads if road.color == color]
				if len(color_roads) == len(color_to_house_mapping):
					color = color+'*'
				if len(color_roads):
					colors.append(f"\t\t{color:<{COLOR_STR_LEN}}: "+', '.join([road.name if not road.is_mortgaged else road.name+'*' for road in color_roads]))
			if len(colors):
				return '\n'+'\n'.join(colors)
			else:
				return ''

		return f"""### Score for {self._name}, in {self._game._game_board[self._position].name} (cell {self._position:>2}) ###
	last dice value:     {self._dice_value:>5}
	cash:                {self._cash:>5}{CURRENCY_SYMBOL}
	mortgageable amount: {self._properties_total_mortgageable_amount:>5}{CURRENCY_SYMBOL}
	owned utilities ({self.get_owned_utilities_count()}): {', '.join([s.name if not s.is_mortgaged else s.name+'*' for s in self._list_owned_utilities])}
	owned stations  ({self.get_owned_stations_count()}): {', '.join([s.name if not s.is_mortgaged else s.name+'*' for s in self._list_owned_stations])}
	owned roads    ({len(self._list_owned_roads):>2}): {get_roads_owned()}
	owned houses: {sum([i[0] for i in self._dict_owned_houses_hotels.values()]) -4*owned_hotels}, owned hotels: {owned_hotels}
###"""


	def set_cash(self, amount):
		self._cash = amount

	def meet_other_players(self, list_players):
		""" Get opponent players. Create dict {'name': Player} of players.

		:param list_players: (list) players objects of the other opponents
		:return:
		"""
		self._list_players = list_players.copy()
		self._list_players.remove(self)

	def have_enough_money(self, amount, plus_mortgageable=False):
		""" Determine if the player has enough money. The required amount is passed as parameter (amount).
			The function can compare the amount against cash only or cash+mortgageable amount.

		:param amount: (int) Cash required
		:param plus_mortgageable: (bool) Compare against cash only (if False) or cash + mortgageable (if True)
		:return: (bool) if True, player has enough money, False otherwise

		# TODO remove this crap, use exceptions instead
		"""
		if plus_mortgageable:
			return amount <= self.cash + self._properties_total_mortgageable_amount
		else:
			return amount <= self._cash

	async def buy_or_bid(self, cell):
		""" Determine whether to buy or to bid the road"""
		match cell.type:
			case 'road':
				return 'buy' if await self.input(f"Do you want to buy '{cell.name}' ({cell.color}) for {cell.price}? ").lower() in ('y','yes') else 'pass'
			case 'station':
				return 'buy' if await self.input(f"Do you want to buy the '{cell.name}' station for {cell.price}? ").lower() in ('y','yes') else 'pass'
			case 'utility':
				return 'buy' if await self.input(f"Do you want to buy the '{cell.name}' utility for {cell.price}? ").lower() in ('y','yes') else 'pass'
			case _:
				raise ValueError(cell.type)

	async def pay_bank(self, amount, reason):
		""" Pay amount to the bank. Money are subtracted from player's cash and added to bank's total cash.

		:param amount: (int) Amount of money to pay
		:return: None
		"""

		if not amount:
			return
		elif amount < 0:
			writeX( self.writer, f"You receive {-amount}{CURRENCY_SYMBOL} from the bank for {reason}.".encode('utf8') )
			await self._game.broadcast(f"{self._name} receives {-amount}{CURRENCY_SYMBOL} from the bank for {reason}.", NOT=(self,))
			self._cash += self._game.bank.withdraw(-amount)
		elif self._cash < amount:
			raise InsufficientFundsAvailable
		else:
			writeX( self.writer, f"You pay the bank {amount}{CURRENCY_SYMBOL} ({reason}).".encode('utf8') )
			await self._game.broadcast(f"{self._name} pays the bank {amount}{CURRENCY_SYMBOL} for {reason}.", NOT=(self,))
			self._cash -= self._game.bank.pay(amount)

	async def pay_tax(self, tax_amount):
		""" Pay tax. This is used when the player ends in a tax cell (income tax or super tax) or when the player
			picks a fee card (e.g., doctor_fees).

		:param tax_amount: (int) Amount of money to pay
		:return: None
		"""

		if self.have_enough_money(tax_amount):
			await self.pay_bank(tax_amount, 'taxes')
		else:
			if not await self.is_bankrupt(tax_amount):
				# TODO check this is consistent
				amount_required = tax_amount - self._cash
				await self.get_money_from_mortgages(amount_required)
				await self.pay_bank(tax_amount, 'taxes')

	async def pay_opponent(self, opponent, amount, reason):
		""" Pay another player.

		:param opponent_name: (String) name of the other opponent
		:param amount: (int) Amount to pay
		:return:
		"""
		assert self._cash >= amount
		await self._game.broadcast(f"{opponent._name} received {amount}{CURRENCY_SYMBOL} from {self._name} for {reason}", NOT = (self, opponent))
		writeX(self.writer, f"You gave {amount}{CURRENCY_SYMBOL} to {opponent._name} {reason}".encode('utf-8') )
		writeX(opponent.writer, f"You received {amount}{CURRENCY_SYMBOL} from {self._name} for {reason}".encode('utf-8') )
		opponent._cash += amount
		self._cash -= amount

	async def pay_each_player(self, amount, reason):
		for o in self._list_players:
			await self.pay_opponent(o, amount, reason)

	async def lose_money(self, cell, notes = (10,20,20,20,50,50,100) ):
		from random import choice
		amount = choice(notes)
		cell.inventory.append(('lost money', amount))
		await self._game.broadcast(f"{self._name} lost {amount}{CURRENCY_SYMBOL} on {cell}.")


	async def buy_property(self, cell):
		""" Buy cell

		:param cell: (dictionary) Cell information
		:return:
		"""

		if cell.type not in ( 'road', 'station', 'utility'):
			writeX( self.writer, f"You cannot purchase {cell.name}.".encode('utf-8') )
			return

		if cell.belongs_to is not None:
			writeX( self.writer, f"This property already belongs to {cell.belongs_to._name}".encode('utf-8') )
			return

		async def exchange(cell):
			# exchange ownership
			cell.belongs_to = self
			self._dict_owned_houses_hotels[cell] = (0, 0)
			self._properties_total_mortgageable_amount += cell.mortgage_value

			if cell.type == 'road':
				self._list_owned_roads.append(cell)
				count_cells_of_color = 0
				for cell in self._list_owned_roads:
					if cell.color == cell.color:
						count_cells_of_color += 1

				if count_cells_of_color == color_property_count[cell.color]:
					self._dict_owned_colors[cell.color] = self
			elif cell.type == 'utility':
				self._list_owned_utilities.append(cell)
			elif cell.type == 'station':
				self._list_owned_stations.append(cell)
			else:
				raise ValueError(cell.type)

			if cell.type == 'road':
				writeX( self.writer, f"You are now the owner of {cell.name} ; rent is currently {cell.estimate_rent(None)}{CURRENCY_SYMBOL}".encode('utf-8'))
			else:
				writeX( self.writer, f"You are now the owner of {cell.name} ; rent is currently uncertain".encode('utf-8'))	# TODO figure sth out for the rent on utility/station (AttributeError: 'NoneType' object has no attribute '_dice_value')

			await self._game.broadcast(f"{self._name} is now the owner of {cell.name} ; rent is currently {cell.estimate_rent(None)}{CURRENCY_SYMBOL}", NOT=(self,))

		try:
			await self.pay_bank(cell.price, cell.name)
		except InsufficientFundsAvailable:
			if not await self.is_bankrupt(cell.price):
				await self.pay_bank(cell.price, cell.name)
				await exchange(cell)
			else:
				await self._game.bcellcast(f"{self._name} has insufficient funds to purchase {cell.name}")
		else:
			await exchange(cell)


	async def pay_rent(self, property_obj, amount):
		""" Pay the rent to the owner of the property.

		:param property_obj: (dict) Property information
		:param amount: (int) Rent amount
		:return:
		"""

		await self.pay_opponent(property_obj.belongs_to, amount*self.rent_multiplicator, 'rent')
		self.rent_multiplicator = 1

	def bid(self, dict_road_info, player_offer):
		""" Counter-bid an offer"""
		# TODO placeholder. To implement.
		return None

	async def mortgage_or_bid(self, cell):
		""" Determine whether to mortgage (to buy) or bid"""
		# TODO This function is incomplete. In reality, the player should decide whether to mortgage or bid to try
		# buying the road at a lower (available) price.
		return 'mortgage' if await self.input(f"Do you want mortgage some properties to buy '{cell.name}' for {cell.price}? ").lower() in ('y','yes') else 'pass'

	async def mortgage(self, property_obj):
		if property_obj.belongs_to != self:
			raise Exception(f"{property_obj.type} {property_obj.name} not owned by player {self._name}")

		property_obj.is_mortgaged = True
		self._list_mortgaged_roads.append(property_obj)

		self._properties_total_mortgageable_amount -= property_obj.mortgage_value
		await self.pay_bank(-property_obj.mortgage_value, 'mortgage')

	async def unmortgage(self, property_obj):
		""" Unmortgage property.

		:param property_obj: (Cell) Property
		: None
		"""
		if property_obj.belongs_to != self:
			raise Exception(f"{property_obj.type} {property_obj.name} not owned by player {self._name}")

		property_obj.is_mortgaged = False
		try:
			self._list_mortgaged_roads.remove(property_obj)
		except ValueError:
			print(f">>> {property_obj} not in {self._list_mortgaged_roads=}")
			raise

		self._properties_total_mortgageable_amount += property_obj.unmortgage_value
		await self.pay_bank(property_obj.unmortgage_value, 'unmortgage')

	async def manage_properties(self):
		""" interactive property management (mortgage/unmortgage/sell) """
		dict_mortgage_properties = {p: False for p in self.list_all_properties}   # temp toggle list

		# TODO house management
		writeX( self.writer, f"Your banker picks up the phone ; his voice is unpleasant and he seems very much annoyed.".encode('utf-8'))

		def list_preselection():
			NAME_WIDTH   = 21
			TOGGLE_WIDTH = 6

			total_change = 0
			lines = ['']

			lines.append(
				f"┌────┬{'─'*(NAME_WIDTH+2)}┬{'─'*(AMOUNT_WIDTH+2)}┬{'─'*(AMOUNT_WIDTH+2)}┬{'─'*(AMOUNT_WIDTH+2)}┬{'─'*(TOGGLE_WIDTH+2)}┐"
			)

			lines.append(
				f"│ ID │ {'Property':<{NAME_WIDTH}} │ "
				f"{'Price':>{AMOUNT_WIDTH}} │ "
				f"{'Mortgage':>{AMOUNT_WIDTH}} │ "
				f"{'Unmortgage':>{AMOUNT_WIDTH}} │ "
				f"{'toggle':^{TOGGLE_WIDTH}} │"
			)

			lines.append(
				f"├────┼{'─'*(NAME_WIDTH+2)}┼{'─'*(AMOUNT_WIDTH+2)}┼{'─'*(AMOUNT_WIDTH+2)}┼{'─'*(AMOUNT_WIDTH+2)}┼{'─'*(TOGGLE_WIDTH+2)}┤"
			)

			for i, (p, selected) in enumerate(dict_mortgage_properties.items()):

				if p.is_mortgaged:
					mortgage = format_amount(None)
					unmortgage = format_amount(p.unmortgage_value, "-")
				else:
					mortgage = format_amount(p.mortgage_value, "+")
					unmortgage = format_amount(None)

				if selected:
					total_change += (
						-p.unmortgage_value if p.is_mortgaged
						else p.mortgage_value
					)

				lines.append(
					f"│ {i:>2} │ "
					f"{p.name:<{NAME_WIDTH}} │ "
					f"{format_amount(p.price)} │ "
					f"{mortgage} │ "
					f"{unmortgage} │ "
					f"{('[*]' if selected else '[-]'):^{TOGGLE_WIDTH}} │"
				)
		
			lines.append(
				f"└────┴{'─'*(NAME_WIDTH+2)}┴{'─'*(AMOUNT_WIDTH+2)}┴{'─'*(AMOUNT_WIDTH+2)}┴{'─'*(AMOUNT_WIDTH+2)}┴{'─'*(TOGGLE_WIDTH+2)}┘"
			)

			lines.append("")
			lines.append(f"{'Selection change':<18}: {format_amount(total_change, '+' if total_change >= 0 else '')}")
			lines.append(f"{'Cash before':<18}: {format_amount(self._cash)}")
			lines.append(f"{'Cash after':<18}: {format_amount(self._cash + total_change)}")

			writeX( self.writer, "\n".join(lines).encode('utf-8'))


		while True:
			list_preselection()

			try:
				p = list(dict_mortgage_properties.keys())[int(res := await self.input("Select property to toggle ; type 'OK' when done."))]
				dict_mortgage_properties[p] = not dict_mortgage_properties[p]
			except (IndexError, ValueError):
				if 'ok'.startswith(res.lower()):
					amount = 0
					for p, v in dict_mortgage_properties.items():
						if v:
							if p.is_mortgaged:
								await self.unmortgage(p)
								amount -= p.unmortgage_value
							else:
								await self.mortgage(p)
								amount += p.mortgage_value
					writeX( self.writer, f"Your banker says your account balance is now {self._cash} (difference is {amount}{CURRENCY_SYMBOL}) and hangs up without saying goodbye. You think to yourself that person is very rude.".encode('utf-8'))
					return
				writeX( self.writer, f"Whut?".encode('utf-8'))


	async def choose_mortgage_properties(self, list_mortgageable_properties, amount):
		""" Return a list of properties to mortgage given a required amount. This function
		doesn't take into account the cash available to the player. Example: if player owns 100$
		and the required amount is 150, the returned properties have a mortgage value >= 150.

		:param amount: (int) Amount required
		:return: (list) list of Cell objects
		"""
		dict_mortgage_properties = {}   # temp toggle list
		dict_mortgage_properties |= {cell:False for cell in self._list_owned_roads	 if not cell.is_mortgaged}
		dict_mortgage_properties |= {cell:False for cell in self._list_owned_stations  if not cell.is_mortgaged}
		dict_mortgage_properties |= {cell:False for cell in self._list_owned_utilities if not cell.is_mortgaged}

		def list_preselection():
			# TODO not quite right... goes with remove choose_unmortgage_properties -> toggle_mortgage_properties
			i, a = 0, 0
			for p, v in dict_mortgage_properties.items():
				writeX( self.writer, f"\t{i:>2}: {p.name:<21} ({p.mortgage_value:>3}{CURRENCY_SYMBOL}){' [mortgage]' if v else '[unmortgage]'}".encode('utf-8'),)
				if v: a = a+p.mortgage_value
				i += 1
			writeX( self.writer, f"Total amount from selection mortgage: {a}{CURRENCY_SYMBOL} (cash after: {self._cash+a}{CURRENCY_SYMBOL})".encode('utf-8'))

		list_preselection()

		while True:
			try:
				p = list(dict_mortgage_properties.keys())[int(res := await self.input("Select property to toggle ; type 'OK' when done."))]
				dict_mortgage_properties[p] = not dict_mortgage_properties[p]
			except (IndexError, ValueError):
				if 'ok'.startswith(res.lower()):
					return [p for p, v in dict_mortgage_properties.items() if dict_mortgage_properties[p]]
				writeX( self.writer, f"Whut?".encode('utf-8'))
			finally:
				list_preselection()


	async def choose_unmortgage_properties(self):
		""" Return a list of properties to unmortgage given the available cash.

		Example: if player owns 130 and owns 'old kent road' (unmortgage value 33) and 'kings cross station'
		(unmortgage value 110), the returned property can be either one or the other (not both).
		In this function the properties are scanned in the following order: roads, stations, utilities. For this reason
		in the example, 'old kent road' would be returned.
		Better (more complex) logic should be implemented.

		:return: (list) list of Cell objects
		"""
		raise NotImplementedError("like choose_mortgage_properties (or get rid of current func)")
		dict_unmortgage_properties = {} # temp list
		dict_unmortgage_properties |= {cell:False for cell in self._list_owned_roads	 if cell.is_mortgaged}
		dict_unmortgage_properties |= {cell:False for cell in self._list_owned_stations  if cell.is_mortgaged}
		dict_unmortgage_properties |= {cell:False for cell in self._list_owned_utilities if cell.is_mortgaged}

		def list_preselection():
			i, a = 0, 0
			for p, v in dict_unmortgage_properties.items():
				cprint(f"\t{i:>2}: {p.name:<21} ({p.mortgage_value:>3})",'white' if v else None)
				if v: a = a+p.unmortgage_value
				i += 1
			print(f"Total amount to unmortgage selection: {a} (available cash: {self._cash-a})")

		list_preselection()

		while True:
			while True:
				try:
					p = list(dict_unmortgage_properties.keys())[int(await self.input("Select property to unmortgage: "))]
					dict_unmortgage_properties[p] = not dict_unmortgage_properties[p]
				except (IndexError, ValueError):
					break
			list_preselection()
			if await self.input('OK? ').lower() in ('y', 'yes'):
				return [p for p, v in dict_unmortgage_properties.items() if v]#dict_unmortgage_properties[p]]

	@property
	def list_all_properties(self):
		#  choose properties to mortgage
		return \
			[road for road in self._list_owned_roads] +\
			[station for station in self._list_owned_stations] +\
			[utility for utility in self._list_owned_utilities]


	async def get_money_from_mortgages(self, amount_required):
		""" Mortgage the necessary (owned) properties to get the amount of money required.
			The process involves:
				* select the properties to mortgage
				* mortgage the properties
		:param amount_required: (int) Amount of money required.
		:return:
		"""

		if self._cash + self._properties_total_mortgageable_amount < amount_required:
			raise InsufficientFundsAvailable('player {} has insufficient funds'.format(self._name))

		list_properties = await self.choose_mortgage_properties(self.list_mortgageable_properties, amount_required)

		#  mortgage properties
		for property_obj in list_properties:
			await self.mortgage(property_obj)

	async def mortgage_and_buy(self, property_obj):
		""" Mortgage the necessary properties to buy the given property

			:param property_obj: (Dictionary) information of the property to buy
			:return:
		"""

		amount_required = property_obj.price - self._cash
		await self.get_money_from_mortgages(amount_required)
		self.buy(property_obj)

	def make_offer(self, opponent):
		""" Make an offer to the owner of the road"""
		# TODO placeholder. To implement.
		return None

	def has_all_roads_of_color(self, color):
		""" Returns True if player owns all the roads of a given color. Return False otherwise. It's use to calculate
			the rent amount that the other player needs to pay when ends in a road cell.
			Example: if player owns 'old kent road' and 'whitechapel road', has_all_road_of_color('brown') -> True

		:param color: (String) Road's color
		:return: (Boolean) True if player owns all the roads of a given color.
		"""
		return True if self._dict_owned_colors[color] is self else False

	def get_houses_hotel_count(self, road):
		""" Given a road name, returns the number of houses or hotel owned.
			Example: if player owns 2 houses in 'old kent road' returns (2, 0).
			Example: if player owns 1 hotel in 'old kent road' returns (0, 1).

		:param road_name: (String) Name of the road
		:return: (tuple) number of houses, number of hotels
		"""
		return self._dict_owned_houses_hotels[road]

	def get_owned_stations_count(self):
		""" Return the number of stations owned.

		:return: (int) Number of stations
		"""

		return len(self._list_owned_stations)

	def get_owned_utilities_count(self):
		""" Return the number of utilities owned.

		:return: (int) Number of utilities
		"""

		return len(self._list_owned_utilities)

	def get_owned_colors(self):
		""" Return a list of colors owned by the player. Note: a color is owned when the player has all the road
			of that specific color.

		:return: (list) List of strings. Example: ['brown', 'blue']
		"""

		list_colors = [color for color in color_to_house_mapping.keys() if self.has_all_roads_of_color(color)]
		return list_colors

	async def is_bankrupt(self, value_to_pay):
		""" Check if player has enough money to pay, or if it needs to declare bankraptcy.

		:param value_to_pay:  (int) Amount of money to pay.
		:return: (bool) True if players is bankrupt, False if it's not.
		"""
		if self._properties_total_mortgageable_amount + self._cash < value_to_pay:
			self._has_lost = True

		elif 'iPhone' not in self.inventory:
			await self._game.broadcast( f"{self._name} doesn't have a phone, can't call their banker and is bankrupt." )
			self._has_lost = True
		else:
			await self.get_money_from_mortgages(value_to_pay)

		self._game.input_queue.put_nowait((self, {'uuids': [None, f"is_bankrupt({self._name}, {value_to_pay}): {self._cash} {self._has_lost=}".encode('utf-8')]}))	# 'context'
		return self._has_lost

	async def want_to_buy_house_hotel(self):
		""" Determine if the player wants to buy a house or a hotel. This function should be used only if the player
			owns at least all the roads of one color (e.g. player owns all the roads with the brown color).

			:return: (bool) True if player decides to buy a house or a hotel.
		"""
		for color in self.owned_colors:
			for road in color_to_house_mapping[color]:
				try:
					houses, hotels = self._dict_owned_houses_hotels[road]
				except KeyError:
					continue
				else:
					if not self._dict_owned_houses_hotels[road][1] and (self._game.bank._hotels or self._game.bank._houses):
						return True if await self.input("Do you want to buy a house or hotel? ").lower() in ('y','yes') else False

	async def want_to_unmortgage(self):
		""" Determine if the player wants to unmortgage a road or a property.

		:return: (bool) True if the player decides to unmortgage roads or properties
		"""
		return True if await self.input("Do you want to unmortgage a property? ").lower() in ('y','yes') else False

	async def choose_house_hotel_to_buy(self):
		""" Select where to buy a house or a hotel. It returns the road name and whether the player should buy a house
			or a hotel. In case the player cannot buy any house or hotel (cause of lack of money or he has
			all houses/hotels already), then None is returned.
			The function checks the following:
				1) which color does the player own
				2) does the player have the maximum amount of houses/hotels for that color (4 houses + 1 hotel in each road)
			The function makes sure that a the road name with the minimum amount of houses is returned.

		:return: (tuple) (road_name, 'house/hotel') The first element indicates the road where to buy, while the second
													one whether to buy a house or a hotel. If player can't buy either,
													(None, None) is returned.
		"""
		#  TODO check if a road is mortgaged ; if yes, it is not possible to buy a house

		# Note: this function is in reality more complex. This is just a temporary logic
		# until a more "intelligent" logic is built. If the players owns more than one color, the function should
		# more intelligently choose the color where to buy a house or hotel.

		l = []
		for color in self._dict_owned_colors:
			for road in color_to_house_mapping[color]:
				try:
					houses, hotels = self._dict_owned_houses_hotels[road]
				except KeyError:
					continue
				else:
					if self._dict_owned_colors[road.color]:
						if sum(self._dict_owned_houses_hotels[road]) < 5:
							# TODO print cost for houses and hotels
							print(f"\t({len(l):>2}) ({road.color}) {road}: {houses=}, {hotels=}")
							l.append(road)

		if len(l):
			while True:
				try:
					p = l[int(await self.input("select index "))]
				except (ValueError, IndexError):
					break
				else:
					if self._game.bank._houses and self._dict_owned_houses_hotels[p][0] < 4:
						print(f"buying a house on {p}")
						await self.buy_house(p)
					elif self._game.bank._hotels and self._dict_owned_houses_hotels[p][1] == 0:
						print(f"buying a hotel on {p}")
						await self.buy_hotel(p)
					else:
						print(f"not more estate available on {p}")

		return None, None

	async def buy_house(self, road):
		""" Buy a house in the given road.

		:param road: (str) road in where to buy the house
		"""
		# TODO like buy_road after get_money_from_mortgages()
		if road.type != 'road' or road.belongs_to is not self:
			raise CannotDoThat( f"This is not a road or you cannot build here" )

		if self._dict_owned_houses_hotels[road][1] == 1:
			raise Exception("Player {} already owns a hotel on '{}'. "
							"No more houses can be bought.".format(self._name, road))
		if self._dict_owned_houses_hotels[road][0] == 4:
			raise Exception("Player {} already owns 4 houses on '{}'. "
							"No more houses can be bought.".format(self._name, road))

		if self._game.bank._houses > 0:
			try:
				await self.pay_bank(road.houses_cost, f"a house on {road.name}.")
			except InsufficientFundsAvailable:
				await self.get_money_from_mortgages(road.houses_cost)
			else:
				houses_owned = self._dict_owned_houses_hotels[road][0]
				self._dict_owned_houses_hotels[road] = (houses_owned + 1, 0)
				self._game.bank._houses -= 1
			await self.broadcast(f"{self._name} bought a house on {road.name} ; rent is now {road.estimate_rent(None)}{CURRENCY_SYMBOL}.")
		else:
			raise NoMoreHousesAvailable

	async def buy_hotel(self, road):
		""" Buy a hotel in the given road.

		:param road: (str) road in where to buy the hotel
		"""
		# TODO like buy_road after get_money_from_mortgages()
		if road.type != 'road' or road.belongs_to is not self:
			raise CannotDoThat( f"This is not a road or you cannot build here" )

		if self._dict_owned_houses_hotels[road][1] == 1:
			raise Exception("Player {} already owns 1 hotel in the road {}. "
							"No more hotels can be bought.".format(self._name, road))

		if self._game.bank._hotels > 0:
			if self._dict_owned_houses_hotels[road][0] != 4:
				raise Exception("Player {} cannot buy a hotel in road {} if "
								"4 houses are not owned first".format(self._name, road))
			await self.pay_bank(road.hotels_cost, f"a hotel on {road.name}")
			self._game.bank._houses += 4
			self._game.bank._hotels -= 1
			self._dict_owned_houses_hotels[road] = (4, 1)

			await self.broadcast(f"{self._name} bought a hotel on {road.name} ; rent is now {road.rent_with_4_houses_1_hotels}{CURRENCY_SYMBOL}.")
		else:
			raise NoMoreHotelsAvailable

	def sell_house_or_hotel(self, road):
		""" sell a house or hotel on the given road

		:param road: (str) road from which to sell the house or hotel

		TODO function not used ATM!
		"""
		if self._dict_owned_houses_hotels[road][1]:
			amount = road.hotels_cost / 2
			self._dict_owned_houses_hotels[road][1] -= 1
			self._cash += self._game.bank.withdraw(amount)
		elif self._dict_owned_houses_hotels[road][0]:
			amount = road.houses_cost
			self._dict_owned_houses_hotels[road][0] -= 1
			self._cash += self._game.bank.withdraw(amount)
		else:
			raise NothingHereToSell

	async def want_to_mortgage_to_buy_house(self):
		""" Determine if player wants to mortgage properties to gain money to buy a house, when the player doesn't
			have enough cash to buy.

		:return: (bool) if True the player mortgages properties to buy a house. False otherwise
		"""
		return True if await self.input("Do you want to mortgage a property to buy a house? ").lower() in ('y','yes') else False

	async def want_to_mortgage_to_buy_hotel(self):
		""" Determine if player wants to mortgage properties to gain money to buy a hotel, when the player doesn't
			have enough cash to buy.

		:return: (bool) if True the player mortgages properties to buy a hotel. False otherwise
		"""
		return True if await self.input("Do you want to mortgage a property to buy a hotel? ").lower() in ('y','yes') else False

	async def go_to_jail(self):
		""" Move the player in the jail cell. Change player position to 10. Used when the player ends in the cell
			30 (go to jail) or when chances and opportunity cards say to do so."""

		# player is a diplomat, and gets away from everything
		for item in self.inventory:
			try:
				if item.name == 'diplomatic papers':
					await self._game.broadcast(f"{self._name} shows their diplomatic papers and tells the constables to fuck off.")
					return False
			except AttributeError:
				# NOTE temporary until real objects for ie iPhone are added ; then remove try/except clause entirely
				pass

		# if player is in debt, make them pay (double)!
		self._jail_count = 3 + 2*sum([amount for opponent, amount in self._debts])//50

		for item in self.inventory:
			try:
				if item.name == 'out of jail':
					if (await self.input("You have an 'out of jail' card ; do you want to use it right away?")).lower() in ('y', 'yes'):
						self.inventory.remove(item)
						item.deck.discard( [await item.use(self)] )
						if not self._jail_count:
							await self._game.broadcast(f"{self._name} pops an 'out of jail' card from behind their ear and gets to walk free.")
							return False
						else:
							await self._game.broadcast(f"{self._name} popped a dirty 'out of jail' card from a pocket but still has debts to pay.")
					else:
						break
			except AttributeError:
				# NOTE temporary until real objects for ie iPhone are added ; then remove try/except clause entirely
				pass


		if 'iPhone' in self.inventory:
			print("# TODO make a single phone call to banker or another player?", self.inventory)

		# TODO dispatch inventory content to jail inventory ; give paper and a pen

		self._position = 10
		writeX( self.writer, f"You are escorted firmly toward the city gaol. Heavy iron gates slam shut behind you. The stone walls are sturdy, the guards alert, and freedom feels frustratingly close.".encode('utf-8') )
		await self._game.broadcast(f"{self._name} is escorted firmly toward the city gaol while people boo and spit on them.", NOT=(self, ) )

		return True
	
	async def chance_jail_card(self):
		# only clears the first days of jail, not those from debts!
		self._jail_count -= 3

	async def get_out_of_jail(self, advance=True):
		""" Player leaves the jail. Jail count is set to zero and the position updated with the latest dices values"""
		self._jail_count = 0
		writeX( self.writer, f"You get out of jail.".encode('utf-8') )
		await self._game.broadcast(f"{self._name} gets out of jail.", NOT=(self, ))

		if advance:
			return await self.advance( self._dice_value )
		else:
			return self._game._game_board[self._position]


	async def pay_to_exit_jail(self):
		""" Determine whether the player wants to wait the next turn or pay to get out of the jail. This is used
			only when the jail_counter is lower than three and the dices didn't return equal values ("roll a double").
		:return: (str) 'wait' if the players decides to wait, 'pay otherwise'
		"""
		return True if await self.input("Do you want to got out of jail? ").lower() in ('y','yes') else False


	async def street_repairs(self, amounts, reason):
		""" Implement logic for the community chest card "street repair", where the player has to pay 40 for each house
			and 115 for each hotel. The player looses the game if there are no enough money available (bankrupt).

		:return:
		"""
		count_houses = 0
		count_hotels = 0
		for color in self.get_owned_colors():
			for road in color_to_house_mapping[color]:
				n_houses, n_hotels = self.get_houses_hotel_count(road)
				count_houses += n_houses
				count_hotels += n_hotels

		total_required_amount = amounts[0] * count_houses + amounts[1] * count_hotels

		if self.have_enough_money(total_required_amount):
			await self.pay_bank(total_required_amount, reason)
		elif self.have_enough_money(total_required_amount, plus_mortgageable=True):
			residual_amount_required = total_required_amount - self.cash
			await self.get_money_from_mortgages(residual_amount_required)
		else:
			await self.is_bankrupt(total_required_amount)


	async def advance(self, distance, reason = None):
		"""move forwards `distance` cells ; collect {GO_AMOUNT} if passing through GO"""
		#cprint(f"advance {self._position} -> {(self._position + distance) % len(self._game._game_board)}", 'yellow')
		self._position = (self._position + distance) % len(self._game._game_board)

		# TODO if catching up with a player in debt, make that other player go in jail

		# check if player passed Go. If yes, get GO_AMOUNT $
		if self._position - self._dice_value < 0:
			try:
				self._cash += self._game.bank.withdraw(GO_AMOUNT)
			except InsufficientFundsAvailable:
				await self._game.broadcast('InsufficientFundsAvailable: bank is game over!')
				raise
				#sleep(1)
			else:
				await self._game.broadcast(f"{self._name} reached 'Go' and collected {GO_AMOUNT}{CURRENCY_SYMBOL}")

		cell = self._game._game_board[self._position]
		self.rent_to_pay = self._game._game_board[self._position].estimate_rent(self)

		if cell.belongs_to == self:
			writeX( self.writer, f"You landed on {cell.name}, home sweet home! ; the weather is {random.choice(['great','so-so','bad','horrible'])}".encode('utf-8') )
			await self._game.broadcast(f"{self._name} landed on {cell.name}, they're at home and the weather is {random.choice(['great','so-so','bad','horrible'])}" , NOT=(self,))
		elif self.rent_to_pay:
			writeX( self.writer, f"You landed on {cell.name}, rent is {self.rent_to_pay}{CURRENCY_SYMBOL} ; the weather is {random.choice(['great','so-so','bad','horrible'])}".encode('utf-8') )
			await self._game.broadcast(f"{self._name} landed on {cell.name}, rent is {self.rent_to_pay}{CURRENCY_SYMBOL} ; the weather is {random.choice(['great','so-so','bad','horrible'])}" , NOT=(self,))
		else:
			try:
				suffix = f"landed on {cell.name} ({cell.color}) ; the weather is {random.choice(['great','so-so','bad','horrible'])}."
			except AttributeError:
				suffix = f"landed on {cell.name} ; the weather is {random.choice(['great','so-so','bad','horrible'])}."
			finally:
				writeX( self.writer, f"You {suffix}".encode('utf-8') )
				await self._game.broadcast(f"{self._name} {suffix}", NOT=(self,) )
		writeX( self.writer, self._game._game_board[self._position].description.encode('utf-8') )

		return cell

	async def go_to(self, where, reason = None):
		if self._position > where: self._position -= len(self._game._game_board)
		return await self.advance(where-self._position)
		#print(f"go_to({where})")


	async def advance_to_nearest(self, what, reason = None):
		i = 0
		while True:
			i += 1
			if self._game._game_board[(self._position+i)%len(self._game._game_board)].type == what:
				return await self.advance(i) # TODO hook for rent changes (see TODO in monosim/board.py)

	async def play(self):
		#cprint(f"It's {self._name}'s turn.",'cyan')
		#print(f"""\tYou are on {self._game._game_board[self._position]}""")

		tuple_dices = self.roll_dice()
		self._dice_value = tuple_dices[0] + tuple_dices[1]
		if self._game._game_board[self._position].type != 'jail' and not self._jail_count:
			board_cell = self.advance(self._dice_value)

		#print(f"""\tYou landed on {self._game._game_board[self._position]} ; the weather is {random.choice(['great','so-so','bad','horrible'])}""")

		# Buy a house or hotel
		if len(self.owned_colors) and await self.want_to_buy_house_hotel():

			road, house_or_hotel = self.choose_house_hotel_to_buy()
			if house_or_hotel == 'house' and self._game.bank._houses and self._dict_owned_houses_hotels[road][0] < 4:
				house_price = road.houses_cost
				if self.have_enough_money(house_price):
					await self.buy_house(road)
				else:
					if self.want_to_mortgage_to_buy_house():
						if self._properties_total_mortgageable_amount + self._cash >= house_price:
							await self.get_money_from_mortgages(house_price)
							await self.buy_house(road)
			elif house_or_hotel == 'hotel' and self._game.bank._hotels > 0 and self._dict_owned_houses_hotels[road][1] == 0:
				hotel_price = road.hotels_cost
				if self.have_enough_money(hotel_price):
					await self.buy_hotel(road)
				else:
					if self.want_to_mortgage_to_buy_hotel():
						if self._properties_total_mortgageable_amount + self._cash >= hotel_price:
							await self.get_money_from_mortgages(hotel_price)
							await self.buy_hotel(road)

		# Unmortgage property # TODO check for sufficient cash before prompting
		if any([len(self._list_mortgaged_roads), len(self._list_mortgaged_stations), len(self._list_mortgaged_utilities)]) and self.want_to_unmortgage():
			for p in await self.choose_unmortgage_properties():
				self.unmortgage(p)

		try:
			# jail logic
			if board_cell.type == 'jail' and self._jail_count:
				self._jail_count -= 1

				# Double roll
				if tuple_dices[0] == tuple_dices[1]:
					await self.get_out_of_jail()

				# Player has been 3 rounds in jail
				elif not self._jail_count:
					if self.have_enough_money(50):
						await self.pay_bank(50)
						await self.get_out_of_jail()
					else:
						if not await self.is_bankrupt(50):
							amount_to_mortgage = 50 - self._cash
							await self.get_money_from_mortgages(amount_to_mortgage)
							await self.pay_bank(50)
							await self.get_out_of_jail()

				# Player decides to pay or wait in jail
				else:
					if await self.pay_to_exit_jail():
						if self.have_enough_money(50):
							await self.pay_bank(50)
							await self.get_out_of_jail()
						elif not await self.is_bankrupt(50):
							await self.get_money_from_mortgages(50)
							await self.pay_bank(50)
							await self.get_out_of_jail()

			# buy/pay_lease/etc..
			elif board_cell.type in ('road', 'station', 'utility'):
				property_name = board_cell.name
				if board_cell.belongs_to == self:
					print(f"Home sweet home, {self._name}!")
				elif board_cell.belongs_to is None:
					if self.have_enough_money(board_cell.price):
						buy_bid = await self.buy_or_bid(board_cell)
						if buy_bid == 'buy' and board_cell.type == 'road':
							await self.buy_road(board_cell)
						elif buy_bid == 'buy' and board_cell.type != 'road':
							await self.buy_property(board_cell)
						else:
							self.bid(board_cell, 'temp')
					elif self.have_enough_money(board_cell.price, plus_mortgageable=True):
						mortgage_bid = await self.mortgage_or_bid(board_cell)
						if mortgage_bid == 'mortgage':
							self.mortgage_and_buy(board_cell)
						else:
							self.bid(board_cell, 'temp')
					else:
						# Players with no money should bid
						self.bid(board_cell, 'temp')
				elif not board_cell.is_mortgaged:
					# Have enough money to rent?
					if self.have_enough_money(rent):
						await self.pay_rent(board_cell, rent)
					else:
						if not await self.is_bankrupt(rent):
							await self.pay_rent(board_cell, rent)

					# self.make_offer(road_owner)  # TODO This should be possible at any time in the game...

			elif board_cell.type in ('go', 'free parking', 'jail'):
				pass

			elif board_cell.type == 'tax':
				await self.pay_tax(board_cell.tax_amount)
				cprint(f"Tax was {board_cell.tax_amount}, thank you and see you soon!",'magenta')

			elif board_cell.type == 'go to jail':
				await self.go_to_jail()

			elif board_cell.type == 'community chest':
				self._game.community_cards_deck.discard( self._game.community_cards_deck.draw(self) )

			elif board_cell.type == 'chance':
				self._game.chance_cards_deck.discard( self._game.chance_cards_deck.draw(self) )

			else:
				raise ValueError(board_cell.type)

		except InsufficientFundsAvailable:
			try:
				await self.get_money_from_mortgages(road.houses_cost)
			except InsufficientFundsAvailable:
				cprint(f"{self._name} is mostly bankrupt with only {self._cash} available and {self._properties_total_mortgageable_amount}",'magenta')
				raise

	@property
	def cash(self):
		return self._cash

	def has_lost(self):
		return self._has_lost


class PlayerBot(Player):
	"""
		a simple bot that takes decisions on its own, requiring no human interaction
	"""
	def __init__(self, name, game, reader, writer, dice_func = None):
		super().__init__(name, game, dice_func = roll_dice_auto)

	async def buy_or_bid(self, dict_road_info):
		""" Determine whether to buy or to bid the road"""
			# TODO placeholder. To implement.
		return 'buy'

	async def mortgage_or_bid(self, dict_road_info):
		""" Determine whether to mortgage (to buy) or bid"""
		# This function is incomplete. In reality, the player should decide whether to mortgage or bid to try buuying
		# the road at a lower (available) price.
		return 'mortgage'


	async def choose_mortgage_properties(self, list_mortgageable_properties, amount):
		# Note: this function is in reality more complex. This is just a temporary logic
		# until a more "intelligent" logic is built.

		idx_property = 1
		mortgage_value = 0
		list_properties = []
		while (mortgage_value < amount) and (idx_property <= len(list_mortgageable_properties)):
			tuple_tmp = (list_mortgageable_properties[idx_property - 1][0], list_mortgageable_properties[idx_property - 1][1])
			list_properties.append(tuple_tmp)
			mortgage_value += list_mortgageable_properties[idx_property - 1][2]
			idx_property += 1

		if mortgage_value < amount:
			raise Exception('player {} total mortgageable amount is insufficient'.format(self._name))

		return list_properties

	async def choose_unmortgage_properties(self):
		total_unmortgage_value = 0
		list_unmortgage_properties = []
		for road_name in self._list_mortgaged_roads:
			unmortgage_value = self._dict_roads[road_name].unmortgage_value
			if unmortgage_value + total_unmortgage_value < self._cash:
				list_unmortgage_properties.append(('road', road_name))
				total_unmortgage_value += unmortgage_value
		for station_name in self._list_mortgaged_stations:
			unmortgage_value = self._dict_properties[station_name].unmortgage_value
			if unmortgage_value + total_unmortgage_value < self._cash:
				list_unmortgage_properties.append(('station', station_name))
				total_unmortgage_value += unmortgage_value
		for utility_name in self._list_mortgaged_utilities:
			unmortgage_value = self._dict_properties[utility_name].unmortgage_value
			if unmortgage_value + total_unmortgage_value < self._cash:
				list_unmortgage_properties.append(('utility', utility_name))
				total_unmortgage_value += unmortgage_value

		return list_unmortgage_properties

	async def want_to_buy_house_hotel(self):
		# Note: this function is in reality more complex. This is just a temporary logic
		# until a more "intelligent" logic is built. For now we let the player decide to buy a house/hotel if it
		# falls in a cell multiple of 5.
		for color in self.owned_colors:
			for road in color_to_house_mapping[color]:
				try:
					houses, hotels = self._dict_owned_houses_hotels[road]
				except KeyError:
					continue
				else:
					if not self._dict_owned_houses_hotels[road][1] and (self._game.bank._hotels or self._game.bank._houses):
						return (self._dice_value % 5 == 0) or (self._dice_value % 5 == 3)

	async def want_to_unmortgage(self):
		return self._dice_value % 2 == 0

	async def choose_house_hotel_to_buy(self):
		for color in self._dict_owned_colors:
			min_count_houses_hotels_in_road = 5

			for road in color_to_house_mapping[color]:
				try:
					houses, hotels = self._dict_owned_houses_hotels[road]
				except KeyError:
					continue
				count_houses_hotels_in_road = houses + hotels
				if count_houses_hotels_in_road < min_count_houses_hotels_in_road:
					min_count_houses_hotels_in_road = count_houses_hotels_in_road
					road_selected = road

			if min_count_houses_hotels_in_road == 5:
				# players has all possible roads and hotels of that color
				pass
			else:
				if min_count_houses_hotels_in_road == 4:
					return road_selected, 'hotel'
				else:
					return road_selected, 'house'

		return None, None

	async def want_to_mortgage_to_buy_house(self):
		# Note: For now we do not allow the player to mortgage properties to buy houses. This is just a placeholder
		# function for now. We will consider more complex logics in the future.
		return False

	async def want_to_mortgage_to_buy_hotel(self):
		# Note: For now we do not allow the player to mortgage properties to buy hotels. This is just a placeholder
		# function for now. We will consider more complex logics in the future.
		return False

	async def pay_to_exit_jail(self):
		return False
