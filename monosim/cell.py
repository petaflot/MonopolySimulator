# vim: noet ts=4 number
from monosim.constants import CURRENCY_SYMBOL

class Cell:
	def __init__(self, kwargs):
		for k, v in kwargs.items():
			setattr(self, k, v)

		self.inventory = []

	def __str__(self):
		return self.name

	def estimate_rent(self, player):
		return 0

	def examine(self):
		# TODO also show other players on the same cell!
		if not len(self.inventory):
			return "	You see nothing here."
		else:
			return "	You see:\n"+'\n\t'.join(f"{item}" for item in self.inventory)

class Road(Cell):
	def __init__(self, *args, kwargs):#, owned_houses_hotels=None):
		super().__init__(*args, kwargs)
		self.belongs_to, self.is_mortgaged = None, None

	"""
		self.owned_houses_hotels = owned_houses_hotels

	def is_buildable(self):
		# TODO also check it player owns all colors!
		return True if self.owned_houses_hotels[1] else False
	"""

	def estimate_rent(self, player):
		""" Given a road, estimate how much rent needs to be paid based on the other player's owned properties.
			For example: if player 2 owns all the roads of a color, return rent 'rent_with_color_set'.

		:return: (int) Rent amount
		"""

		if self.belongs_to is None or player is self.belongs_to:
			return 0

		if self.belongs_to.has_all_roads_of_color(self.color):
			houses, hotel = self.belongs_to.get_houses_hotel_count(self)
			if hotel == 0 and houses == 0:
				rent = self.rent_with_color_set
			else:
				try:
					rent = getattr( self, 'rent_with_{}_houses_{}_hotels'.format(houses, hotel))
				except KeyError:
					print(self.keys())
					raise
		else:
			rent = self.rent

		return rent

	def examine(self):
		# TODO "highlight" current rent
		return f"""This is {self.name} ({self.color}) ; it is {'not owned by anyone' if self.belongs_to is None else f"owned by {self.belongs_to._name}"}
	Price:			 {self.price:>5}{CURRENCY_SYMBOL}
	Mortgage value:	{self.mortgage_value:>5}{CURRENCY_SYMBOL}
	Unmortgage value:  {self.unmortgage_value:>5}{CURRENCY_SYMBOL}
	Rent:			  {self.rent:>5}{CURRENCY_SYMBOL} ({self.rent_with_color_set}{CURRENCY_SYMBOL})
		with 1 house:  {self.rent_with_1_houses_0_hotels:>5}{CURRENCY_SYMBOL}
		with 2 houses: {self.rent_with_2_houses_0_hotels:>5}{CURRENCY_SYMBOL}
		with 3 houses: {self.rent_with_3_houses_0_hotels:>5}{CURRENCY_SYMBOL}
		with 4 houses: {self.rent_with_4_houses_0_hotels:>5}{CURRENCY_SYMBOL}
		with 1 hotel:  {self.rent_with_4_houses_1_hotels:>5}{CURRENCY_SYMBOL}
	Building costs:
		house:		 {self.houses_cost:>5}{CURRENCY_SYMBOL}
		hotel:		 {self.hotels_cost:>5}{CURRENCY_SYMBOL}

""" + super().examine()

class Utility(Cell):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.belongs_to, self.is_mortgaged = None, None

	def estimate_rent(self, player):
		""" Given a utility, estimate how much rent needs to be paid based on the other player's owned properties.
			Example: if player owns the Electric company, return rent = 4 * dice_value.
			Example: if player owns the Electric company and Water work, return rent = 10 * dice_value.

		:return: (int) Rent amount
		"""

		if self.belongs_to is None or player is self.belongs_to:
			return 0

		num_of_utilities = self.belongs_to.get_owned_utilities_count()

		if num_of_utilities == 1:
			return player._dice_value * 4
		elif num_of_utilities == 2:
			return player._dice_value * 10
		else:
			raise Exception("The maximum number of utilities is 2.")

	def examine(self):
		return f"""This is {self.name} ; it is {'not owned by anyone' if self.belongs_to is None else f"owned by {self.belongs_to._name}"}
	Price:			 {self.price:>5}{CURRENCY_SYMBOL}
	Mortgage value:	{self.mortgage_value:>5}{CURRENCY_SYMBOL}
	Unmortgage value:  {self.unmortgage_value:>5}{CURRENCY_SYMBOL}
	Rent:			  dice value * 4 (dice value * 10)

""" + super().examine()

class Station(Cell):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.belongs_to, self.is_mortgaged = None, None

	def estimate_rent(self, player):
		""" Given a station, estimate how much rent needs to be paid based on the other player's owned properties.
			Example: if player owns two stations, return rent = 50.

		:return: (int) Rent amount
		"""

		if self.belongs_to is None or player is self.belongs_to:
			return 0

		num_of_stations = self.belongs_to.get_owned_stations_count()

		if num_of_stations == 1:
			return 25
		elif num_of_stations == 2:
			return 50
		elif num_of_stations == 3:
			return 100
		elif num_of_stations == 4:
			return 200
		else:
			raise Exception("The maximum number of stations is 4.")

	def examine(self):
		# TODO "highlight" current rent
		return f"""This is {self.name} ; it is {'not owned by anyone' if self.belongs_to is None else f"owned by {self.belongs_to._name}"}
	Price:			 {self.price:>5}{CURRENCY_SYMBOL}
	Mortgage value:	{self.mortgage_value:>5}{CURRENCY_SYMBOL}
	Unmortgage value:  {self.unmortgage_value:>5}{CURRENCY_SYMBOL}
	Rent:				25{CURRENCY_SYMBOL} / 50{CURRENCY_SYMBOL} / 100{CURRENCY_SYMBOL} / 200{CURRENCY_SYMBOL}

""" + super().examine()

