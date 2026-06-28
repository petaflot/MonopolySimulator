# vim: number
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

def roll_dice_physical(d=6,n=2):
    """ Takes input from a real dice roll

    :return: (tuple) two int values between 1 and 6 drawn from a uniform distribution.
    """
    while True:
        try:
            res = [int(i) for i in input(f"Roll {n} dice and type result (coma-separated): ").split(',')]
            if len(res) != n:
                raise ValueError
            if min(res) < 1 and max(res) > d:
                raise ValueError
        except ValueError:
            print(f"Invalid draw")
        else:
            return res


def roll_dice_auto(d=6,n=2):
    """ Simulate the roll of two dice. Returns two int values between 1 and 6.

    :return: (tuple) two int values between 1 and 6 drawn from a uniform distribution.
    """

    return tuple([random.randint(1, d) for _ in range(n)])

"""
    NOTE: for algorithmic simplicity, house count on a street stays at 4 if a hotel is built
"""

from monosim.board import get_color_to_house_mapping
color_to_house_mapping, color_property_count = get_color_to_house_mapping()

class Player:
    _dict_owned_colors = {'brown': None, 'light_blue': None, 'purple': None, 'orange': None,
                               'red': None, 'yellow': None, 'green': None, 'blue': None}

    def __init__(self, name, number, bank, game_board, community_cards_deck, chance_cards_deck, dice_func = None):
        self._name = name
        self._number = number
        self._game_board = game_board

        self._position = 0
        self._dice_value = 0
        self._cash = 1500
        self._properties_total_mortgageable_amount = 0
        self._player_cards = []
        self._jail_count = 0
        self._free_visit = False
        self._bank = bank
        self._list_players = None
        self._list_owned_roads = []
        self._list_owned_stations = []
        self._list_owned_utilities = []
        self._list_mortgaged_roads = []
        self._list_mortgaged_stations = []
        self._list_mortgaged_utilities = []
        self._dict_owned_houses_hotels = {}
        self._has_lost = False
        self.community_cards_deck = community_cards_deck
        self.chance_cards_deck = chance_cards_deck

        self.roll_dice = roll_dice_physical if dice_func is None else dice_func

    @property
    def owned_colors(self):
        return tuple([c for c, player in self._dict_owned_colors.items() if player is self])

    def get_state(self):
        """ Get the player's state. The state contains information such as position, roads owned, money, mortgaged
            properties, etc.

        :return: (dictionary) key: property, value: property value (e.g. {'cash': 100, 'position': 10, ...})
        """
        return {'name': self._name, 'number': self._number, 'position': self._position,
                'dice_value': self._dice_value, 'cash': self._cash,
                'mortgageable_amount': self._properties_total_mortgageable_amount, 'jail_count': self._jail_count,
                'player_cards': self._player_cards, 'free_visit': self._free_visit, 'owned_roads': self._list_owned_roads,
                'owned_stations': self._list_owned_stations, 'owned_utilities': self._list_owned_utilities,
                'mortgaged_roads': self._list_mortgaged_roads, 'mortgaged_stations': self._list_mortgaged_stations,
                'mortgaged_utilities': self._list_mortgaged_utilities, 'owned_colors': self.owned_colors,
                'owned_houses_hotels': self._dict_owned_houses_hotels, 'has_lost': self._has_lost,
                'bank_cash': self._bank.cash}

    def get_print_state(self):
        from termcolor import colored
        owned_hotels = sum([i[1] for i in self._dict_owned_houses_hotels.values()])

        return f"""{self._name}, dice value {self._dice_value:>2}, cash {self._cash:>5}, mortgageable amount {self._properties_total_mortgageable_amount:>5}, in position {self._position:>2} ({self._game_board[self._position].name})
    owned_roads: {', '.join([f"{r} ({r.color})" if r not in self._list_mortgaged_roads else colored(r,'grey') for r in self._list_owned_roads])},
    owned_roads={len(self._list_owned_roads)}, owned_utilities={self.get_owned_utilities_count()}, owned_stations={self.get_owned_stations_count()}, owned_houses={sum([i[0] for i in self._dict_owned_houses_hotels.values()]) -4*owned_hotels}, owned_hotels={owned_hotels}, {self.owned_colors = }"""


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

    def buy_or_bid(self, cell):
        """ Determine whether to buy or to bid the road"""
        match cell.type:
            case 'road':
                return 'buy' if input(f"Do you want to buy '{cell.name}' ({cell.color}) for {cell.price}? ").lower() in ('y','yes') else 'pass'
            case 'station':
                return 'buy' if input(f"Do you want to buy the '{cell.name}' station for {cell.price}? ").lower() in ('y','yes') else 'pass'
            case 'utility':
                return 'buy' if input(f"Do you want to buy the '{cell.name}' utility for {cell.price}? ").lower() in ('y','yes') else 'pass'
            case _:
                raise ValueError(cell.type)

    def pay_bank(self, amount):
        """ Pay amount to the bank. Money are subtracted from player's cash and added to bank's total cash.

        :param amount: (int) Amount of money to pay
        :return: None
        """

        if amount < 0:
            self._cash += self._bank.withdraw(-amount)
        else:
            self._cash -= self._bank.pay(amount)

    def pay_tax(self, tax_amount):
        """ Pay tax. This is used when the player ends in a tax cell (income tax or super tax) or when the player
            picks a fee card (e.g., doctor_fees).

        :param tax_amount: (int) Amount of money to pay
        :return: None
        """

        if self.have_enough_money(tax_amount):
            self.pay_bank(tax_amount)
        else:
            if not self.is_bankrupt(tax_amount):
                # TODO check this is consistent
                amount_required = tax_amount - self._cash
                self.get_money_from_mortgages(amount_required)
                self.pay_bank(tax_amount)

    def pay_opponent(self, opponent, amount):
        """ Pay another player.

        :param opponent_name: (String) name of the other opponent
        :param amount: (int) Amount to pay
        :return:
        """
        assert self._cash >= amount
        cprint(f"{opponent._name} received {amount} from {self._name}",'green',)
        opponent._cash += amount
        self._cash -= amount

    def pay_each_player(self, amount):
        for o in self._list_players:
            self.pay_opponent(o, amount)

    def buy(self, road):
        """ Buy road

        :param road: (dictionary) Road information
        :return:
        """

        try:
            self.pay_bank(road.price)
        except InsufficientFundsAvailable:
            if not self.is_bankrupt(road.price):
                raise NotImplementedError
            else:
                raise
        else:
            # exchange ownership
            road.belongs_to = self
            self._list_owned_roads.append(road)
            self._dict_owned_houses_hotels[road] = (0, 0)
            # mortgage value
            self._properties_total_mortgageable_amount += road.mortgage_value

            count_roads_of_color = 0
            for road in self._list_owned_roads:
                if road.color == road.color:
                    count_roads_of_color += 1

            if count_roads_of_color == color_property_count[road.color]:
                self._dict_owned_colors[road.color] = self

    def buy_property(self, property_obj):
        """ Buy property (station or utility)

        :param property_obj: (dictionary) Property information
        :return:
        """
        try:
            self.pay_bank(property_obj.price)
        except InsufficientFundsAvailable:
            if not self.is_bankrupt(property_obj.price):
                raise NotImplementedError
            else:
                raise
        else:
            # exchange ownership
            property_obj.belongs_to = self
            if property_obj.type == 'station':
                self._list_owned_stations.append(property_obj)
            elif property_obj.type == 'utility':
                self._list_owned_utilities.append(property_obj)
            else:
                raise Exception('Property type {} does not exist'.format(property_obj.type))
            # mortgage value
            self._properties_total_mortgageable_amount += property_obj.mortgage_value

    def pay_rent(self, property_obj, amount):
        """ Pay the rent to the owner of the property.

        :param property_obj: (dict) Property information
        :param amount: (int) Rent amount
        :return:
        """

        self.pay_opponent(property_obj.belongs_to, amount)

    def bid(self, dict_road_info, player_offer):
        """ Counter-bid an offer"""
        # TODO placeholder. To implement.
        return None

    def mortgage_or_bid(self, cell):
        """ Determine whether to mortgage (to buy) or bid"""
        # TODO This function is incomplete. In reality, the player should decide whether to mortgage or bid to try
        # buying the road at a lower (available) price.
        return 'mortgage' if input(f"Do you want mortgage some properties to buy '{cell.name}' for {cell.price}? ").lower() in ('y','yes') else 'pass'

    def mortgage(self, property_obj):
        if property_obj.belongs_to != self:
            raise Exception(f"{property_obj.type} {property_obj.name} not owned by player {self._name}")

        property_obj.is_mortgaged = True
        self._list_mortgaged_roads.append(property_obj)

        self._properties_total_mortgageable_amount -= property_obj.mortgage_value
        self.pay_bank(-property_obj.mortgage_value)

    def unmortgage(self, property_obj):
        """ Unmortgage property.

        :param property_obj: (Cell) Property
        :return: None
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
        self.pay_bank(property_obj.unmortgage_value)

    def choose_mortgage_properties(self, list_mortgageable_properties, amount):
        """ Return a list of properties to mortgage given a required amount. This function
        doesn't take into account the cash available to the player. Example: if player owns 100$
        and the required amount is 150, the returned properties have a mortgage value >= 150.

        :param amount: (int) Amount required
        :return: (list) list of Cell objects
        """
        dict_mortgage_properties = {}   # temp list
        dict_mortgage_properties |= {cell:False for cell in self._list_owned_roads     if not cell.is_mortgaged}
        dict_mortgage_properties |= {cell:False for cell in self._list_owned_stations  if not cell.is_mortgaged}
        dict_mortgage_properties |= {cell:False for cell in self._list_owned_utilities if not cell.is_mortgaged}

        def list_preselection():
            i, a = 0, 0
            for p, v in dict_mortgage_properties.items():
                cprint(f"\t{i:>2}: {p.name:<21} ({p.mortgage_value:>3})",'white' if v else None)
                if v: a = a+p.mortgage_value
                i += 1
            print(f"Total amount from selection mortgage: {a} (cash after: {self._cash+a})")

        list_preselection()

        while True:
            while True:
                try:
                    p = list(dict_mortgage_properties.keys())[int(input("Select property to mortgage: "))]
                    dict_mortgage_properties[p] = not dict_mortgage_properties[p]
                except (IndexError, ValueError):
                    break
            list_preselection()
            if input('OK? ').lower() in ('y', 'yes'):
                return [p for p, v in dict_mortgage_properties.items() if dict_mortgage_properties[p]]


    def choose_unmortgage_properties(self):
        """ Return a list of properties to unmortgage given the available cash.

        Example: if player owns 130 and owns 'old kent road' (unmortgage value 33) and 'kings cross station'
        (unmortgage value 110), the returned property can be either one or the other (not both).
        In this function the properties are scanned in the following order: roads, stations, utilities. For this reason
        in the example, 'old kent road' would be returned.
        Better (more complex) logic should be implemented.

        :return: (list) list of Cell objects
        """
        dict_unmortgage_properties = {} # temp list
        dict_unmortgage_properties |= {cell:False for cell in self._list_owned_roads     if cell.is_mortgaged}
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
                    p = list(dict_unmortgage_properties.keys())[int(input("Select property to unmortgage: "))]
                    dict_unmortgage_properties[p] = not dict_unmortgage_properties[p]
                except (IndexError, ValueError):
                    break
            list_preselection()
            if input('OK? ').lower() in ('y', 'yes'):
                return [p for p, v in dict_unmortgage_properties.items() if v]#dict_unmortgage_properties[p]]


    def get_money_from_mortgages(self, amount_required):
        """ Mortgage the necessary (owned) properties to get the amount of money required.
            The process involves:
                * select the properties to mortgage
                * mortgage the properties
        :param amount_required: (int) Amount of money required.
        :return:
        """

        if self._cash + self._properties_total_mortgageable_amount < amount_required:
            raise InsufficientFundsAvailable('player {} has insufficient funds'.format(self._name))

        #  choose properties to mortgage
        list_mortgageable_properties = \
            [road for road in self._list_owned_roads if road.is_mortgaged is False] +\
            [station for station in self._list_owned_stations if station.is_mortgaged is False] +\
            [utiliy for utility in self._list_owned_utilities if utility.is_mortgaged is False]

        if len(list_mortgageable_properties) == 0:
            raise Exception('player {} has no properties to mortgage'.format(self._name))

        list_properties = self.choose_mortgage_properties(list_mortgageable_properties, amount_required)

        #  mortgage properties
        for property_obj in list_properties:
            self.mortgage(property_obj)

    def mortgage_and_buy(self, property_obj):
        """ Mortgage the necessary properties to buy the given property

            :param property_obj: (Dictionary) information of the property to buy
            :return:
        """

        amount_required = property_obj.price - self._cash
        self.get_money_from_mortgages(amount_required)
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

    def get_houses_hotel_count(self, road_name):
        """ Given a road name, returns the number of houses or hotel owned.
            Example: if player owns 2 houses in 'old kent road' returns (2, 0).
            Example: if player owns 1 hotel in 'old kent road' returns (0, 1).

        :param road_name: (String) Name of the road
        :return: (tuple) number of houses, number of hotels
        """
        return self._dict_owned_houses_hotels[road_name]

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

    def is_bankrupt(self, value_to_pay):
        """ Check if player has enough money to pay, or if it needs to declare bankraptcy.

        :param value_to_pay:  (int) Amount of money to pay.
        :return: (bool) True if players is bankrupt, False if it's not.
        """
        if self._properties_total_mortgageable_amount + self._cash < value_to_pay:
            self._has_lost = True
        else:
            self.get_money_from_mortgages(value_to_pay)
            
        print(f"is_bankrupt({self._name}, {value_to_pay}): {self._cash} {self._has_lost=}")
        return self._has_lost

    def want_to_buy_house_hotel(self):
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
                    if not self._dict_owned_houses_hotels[road][1] and (self._bank._hotels or self._bank._houses):
                        return True if input("Do you want to buy a house or hotel? ").lower() in ('y','yes') else False

    def want_to_unmortgage(self):
        """ Determine if the player wants to unmortgage a road or a property.

        :return: (bool) True if the player decides to unmortgage roads or properties
        """
        return True if input("Do you want to unmortgage a property? ").lower() in ('y','yes') else False

    def choose_house_hotel_to_buy(self):
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
                    p = l[int(input("select index "))]
                except (ValueError, IndexError):
                    break
                else:
                    if self._bank._houses and self._dict_owned_houses_hotels[p][0] < 4:
                        print(f"buying a house on {p}")
                        self.buy_house(p)
                    elif self._bank._hotels and self._dict_owned_houses_hotels[p][1] == 0:
                        print(f"buying a hotel on {p}")
                        self.buy_hotel(p)
                    else:
                        print(f"not more estate available on {p}")

        return None, None

    def buy_house(self, road):
        """ Buy a house in the given road.

        :param road: (str) road in where to buy the house
        """
        if self._dict_owned_houses_hotels[road][1] == 1:
            raise Exception("Player {} already owns a hotel on the road {}. "
                            "No more houses can be bought.".format(self._name, road))
        if self._dict_owned_houses_hotels[road][0] == 4:
            raise Exception("Player {} already owns 4 houses on the road {}. "
                            "No more houses can be bought.".format(self._name, road))

        if self._bank._houses > 0:
            try:
                self.pay_bank(road.houses_cost)
            except InsufficientFundsAvailable:
                self.get_money_from_mortgages(road.houses_cost)
            else:
                houses_owned = self._dict_owned_houses_hotels[road][0]
                self._dict_owned_houses_hotels[road] = (houses_owned + 1, 0)
                self._bank._houses -= 1
        else:
            raise NoMoreHousesAvailable

    def buy_hotel(self, road):
        """ Buy a hotel in the given road.

        :param road: (str) road in where to buy the hotel
        """

        if self._dict_owned_houses_hotels[road][1] == 1:
            raise Exception("Player {} already owns 1 hotel in the road {}. "
                            "No more hotels can be bought.".format(self._name, road))

        if self._bank._hotels > 0:
            if self._dict_owned_houses_hotels[road][0] != 4:
                raise Exception("Player {} cannot buy a hotel in road {} if "
                                "4 houses are not owned first".format(self._name, road))
            self.pay_bank(road.hotels_cost)
            self._bank._houses += 4
            self._bank._hotels -= 1
            self._dict_owned_houses_hotels[road] = (4, 1)
        else:
            raise NoMoreHotelsAvailable

    def sell_house_or_hotel(self, road):
        """ sell a house or hotel on the given road

        :param road: (str) road from which to sell the house or hotel

        TODO function not uased ATM!
        """
        if self._dict_owned_houses_hotels[road][1]:
            amount = road.hotels_cost / 2
            self._dict_owned_houses_hotels[road][1] -= 1
            self._cash += self._bank.withdraw(amount)
        elif self._dict_owned_houses_hotels[road][0]:
            amount = road.houses_cost
            self._dict_owned_houses_hotels[road][0] -= 1
            self._cash += self._bank.withdraw(amount)
        else:
            raise NothingHereToSell

    def want_to_mortgage_to_buy_house(self):
        """ Determine if player wants to mortgage properties to gain money to buy a house, when the player doesn't
            have enough cash to buy.

        :return: (bool) if True the player mortgages properties to buy a house. False otherwise
        """
        return True if input("Do you want to mortgage a property to buy a house? ").lower() in ('y','yes') else False

    def want_to_mortgage_to_buy_hotel(self):
        """ Determine if player wants to mortgage properties to gain money to buy a hotel, when the player doesn't
            have enough cash to buy.

        :return: (bool) if True the player mortgages properties to buy a hotel. False otherwise
        """
        return True if input("Do you want to mortgage a property to buy a hotel? ").lower() in ('y','yes') else False

    def go_to_jail(self):
        """ Move the player in the jail cell. Change player position to 10. Used when the player ends in the cell
            30 (go to jail) or when chances and opportunity cards say to do so."""
        self._jail_count = 3
        self._position = 10

    def get_out_of_jail(self):
        """ Player leaves the jail. Jail count is set to zero and the position updated with the latest dices values"""
        self._jail_count = 0
        self._position = (self._position + self._dice_value)

    def pay_to_exit_jail(self):
        """ Determine whether the player wants to wait the next turn or pay to get out of the jail. This is used
            only when the jail_counter is lower than three and the dices didn't return equal values ("roll a double").
        :return: (str) 'wait' if the players decides to wait, 'pay otherwise'
        """
        return True if input("Do you want to got out of jail? ").lower() in ('y','yes') else False

    def street_repairs(self, amounts):
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
            self.pay_bank(total_required_amount)
        elif self.have_enough_money(total_required_amount, plus_mortgageable=True):
            residual_amount_required = total_required_amount - self.cash
            self.get_money_from_mortgages(residual_amount_required)
        else:
            self.is_bankrupt(total_required_amount)


    def advance(self, distance):
        """move forwards `distance` cells ; collect 200 if passing through GO"""
        #cprint(f"advance {self._position} -> {(self._position + distance) % len(self._game_board)}", 'yellow')
        self._position = (self._position + distance) % len(self._game_board)

        # check if player passed Go. If yes, get 200 $
        if self._position - self._dice_value < 0:
            try:
                self._cash += self._bank.withdraw(200)
            except InsufficientFundsAvailable:
                cprint('InsufficientFundsAvailable: bank is game over!','cyan')
                raise
                #sleep(1)
            else:
                cprint(f"GO: {self._name} collected 200", 'green')

    def go_to(self, where):
        if self._position > where: self._position -= len(self._game_board)
        self.advance(where-self._position)


    def advanceToNearest(self, what):
        i = 0
        while True:
            i += 1
            if self._game_board[(self._position+i)%len(self._game_board)].type == what:
                self.advance(i) # TODO hook for rent changes (see TODO in monosim/board.py)
                return

    def play(self):
        cprint(f"It's {self._name}'s turn.",'cyan')
        print(f"""\tYou are on {self._game_board[self._position]} ; the weather is {random.choice(['okay','not great','bad','horrible','worse'])}""")

        tuple_dices = self.roll_dice()
        self._dice_value = tuple_dices[0] + tuple_dices[1]
        if self._position != 10 or (self._position == 10 and self._free_visit):  # TODO if player is not in jail
            self.advance(self._dice_value)
            self._free_visit = True if self._position == 10 else False

        board_cell = self._game_board[self._position]
        print(f"""\tYou landed on {self._game_board[self._position]} ; the weather is {random.choice(['great','so-so','bad','horrible'])}""")

        # Buy a house or hotel
        if len(self.owned_colors) and self.want_to_buy_house_hotel():

            road, house_or_hotel = self.choose_house_hotel_to_buy()
            if house_or_hotel == 'house' and self._bank._houses and self._dict_owned_houses_hotels[road][0] < 4:
                house_price = road.houses_cost
                if self.have_enough_money(house_price):
                    self.buy_house(road)
                else:
                    if self.want_to_mortgage_to_buy_house():
                        if self._properties_total_mortgageable_amount + self._cash >= house_price:
                            self.get_money_from_mortgages(house_price)
                            self.buy_house(road)
            elif house_or_hotel == 'hotel' and self._bank._hotels > 0 and self._dict_owned_houses_hotels[road][1] == 0:
                hotel_price = road.hotels_cost
                if self.have_enough_money(hotel_price):
                    self.buy_hotel(road)
                else:
                    if self.want_to_mortgage_to_buy_hotel():
                        if self._properties_total_mortgageable_amount + self._cash >= hotel_price:
                            self.get_money_from_mortgages(hotel_price)
                            self.buy_hotel(road)

        # Unmortgage property # TODO check for sufficient cash before prompting
        if any([len(self._list_mortgaged_roads), len(self._list_mortgaged_stations), len(self._list_mortgaged_utilities)]) and self.want_to_unmortgage():
            for p in self.choose_unmortgage_properties():
                self.unmortgage(p)

        try:
            # jail logic
            if board_cell.type == 'jail' and self._jail_count:
                self._jail_count -= 1

                # Double roll
                if tuple_dices[0] == tuple_dices[1]:
                    self.get_out_of_jail()

                # Player has been 3 rounds in jail
                elif not self._jail_count:
                    if self.have_enough_money(50):
                        self.pay_bank(50)
                        self.get_out_of_jail()
                    else:
                        if not self.is_bankrupt(50):
                            amount_to_mortgage = 50 - self._cash
                            self.get_money_from_mortgages(amount_to_mortgage)
                            self.pay_bank(50)
                            self.get_out_of_jail()

                # Player decides to pay or wait in jail
                else:
                    if self.pay_to_exit_jail():
                        if self.have_enough_money(50):
                            self.pay_bank(50)
                            self.get_out_of_jail()
                        elif not self.is_bankrupt(50):
                            self.get_money_from_mortgages(50)
                            self.pay_bank(50)
                            self.get_out_of_jail()

            # buy/pay_lease/etc..
            elif board_cell.type in ('road', 'station', 'utility'):
                property_name = board_cell.name
                if board_cell.belongs_to == self:
                    print(f"Home sweet home, {self._name}!")
                elif board_cell.belongs_to is None:
                    if self.have_enough_money(board_cell.price):
                        buy_bid = self.buy_or_bid(board_cell)
                        if buy_bid == 'buy' and board_cell.type == 'road':
                            self.buy(board_cell)
                        elif buy_bid == 'buy' and board_cell.type != 'road':
                            self.buy_property(board_cell)
                        else:
                            self.bid(board_cell, 'temp')
                    elif self.have_enough_money(board_cell.price, plus_mortgageable=True):
                        mortgage_bid = self.mortgage_or_bid(board_cell)
                        if mortgage_bid == 'mortgage':
                            self.mortgage_and_buy(board_cell)
                        else:
                            self.bid(board_cell, 'temp')
                    else:
                        # Players with no money should bid
                        self.bid(board_cell, 'temp')
                elif not board_cell.is_mortgaged:
                    # Have enough money to rent?
                    rent = board_cell.estimate_rent(self)
                    if self.have_enough_money(rent):
                        self.pay_rent(board_cell, rent)
                    else:
                        if not self.is_bankrupt(rent):
                            self.pay_rent(board_cell, rent)

                    # self.make_offer(road_owner)  # TODO This should be possible at any time in the game...

            elif board_cell.type == 'go' or board_cell.type == 'free parking':
                pass

            elif board_cell.type == 'tax':
                self.pay_tax(board_cell.tax_amount)
                cprint(f"Tax was {board_cell.tax_amount}, thank you and see you soon!",'magenta')

            elif board_cell.type == 'go to jail':
                self.go_to_jail()

            elif board_cell.type == 'community chest':
                self.community_cards_deck.discard( self.community_cards_deck.draw(self) )

            elif board_cell.type == 'chance':
                self.chance_cards_deck.discard( self.chance_cards_deck.draw(self) )

            elif board_cell.type == 'jail':
                pass

            else:
                raise ValueError(board_cell.type)

        except InsufficientFundsAvailable:
            try:
                self.get_money_from_mortgages(road.houses_cost)
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
    def __init__(self, name, number, bank, game_board, community_cards_deck, chance_cards_deck, dice_func = None):
        super().__init__(name, number, bank, game_board, community_cards_deck, chance_cards_deck, dice_func = roll_dice_auto)

    def buy_or_bid(self, dict_road_info):
        """ Determine whether to buy or to bid the road"""
            # TODO placeholder. To implement.
        return 'buy'

    def mortgage_or_bid(self, dict_road_info):
        """ Determine whether to mortgage (to buy) or bid"""
        # This function is incomplete. In reality, the player should decide whether to mortgage or bid to try buuying
        # the road at a lower (available) price.
        return 'mortgage'

    def choose_mortgage_properties(self, list_mortgageable_properties, amount):
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

    def choose_unmortgage_properties(self):
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

    def want_to_buy_house_hotel(self):
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
                    if not self._dict_owned_houses_hotels[road][1] and (self._bank._hotels or self._bank._houses):
                        return (self._dice_value % 5 == 0) or (self._dice_value % 5 == 3)

    def want_to_unmortgage(self):
        return self._dice_value % 2 == 0

    def choose_house_hotel_to_buy(self):
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

    def want_to_mortgage_to_buy_house(self):
        # Note: For now we do not allow the player to mortgage properties to buy houses. This is just a placeholder
        # function for now. We will consider more complex logics in the future.
        return False

    def want_to_mortgage_to_buy_hotel(self):
        # Note: For now we do not allow the player to mortgage properties to buy hotels. This is just a placeholder
        # function for now. We will consider more complex logics in the future.
        return False

    def pay_to_exit_jail(self):
        return False
