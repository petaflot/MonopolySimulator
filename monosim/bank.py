# vim: noet ts=4 number
from monosim.custom_exceptions import *

class Bank:
	def __init__(self, cash = 5000, houses = 32, hotels = 12):
		self._cash = cash
		self._houses = houses
		self._hotels = hotels

	@property
	def cash(self):
		return self._cash

	def pay(self, amount):
		if amount < 0: raise ValueError
		self._cash += amount
		return amount

	def withdraw(self, amount):
		if amount < 0: raise ValueError
		if amount > self._cash:
			raise InsufficientFundsAvailable(amount)
		self._cash -= amount
		return amount

	"""
	@property
	def houses(self):
		return self._houses

	@houses.setter
	def houses(self, value):
		if value > self._houses:
			value, self._houses = self._houses, 0
		else:
			self._houses -= value
		return value

	@property
	def hotels(self):
		return self._hotels

	@hotels.setter
	def hotels(self, value):
		if value > self._hotels:
			value, self._hotels = self._hotels, 0
		else:
			self._houses -= value
		return value
	"""

