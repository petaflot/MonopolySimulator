class GotAction(Exception):
    def __init__(self, card, action):
        card.action = action

from random import randint
from termcolor import cprint

class Deck:
    def __init__(self, name, cards ):
        self.name = name
        self.cards = []
        self.discard_pile = cards
        print(f"{self} initialized with {len(cards)} cards")

    def __str__(self):
        return f"<Stack: {self.name} ({len(self.cards)}:{len(self.discard_pile)})>"

    def draw(self, player, n=1):
        if not len(self.cards):
            cprint(f"{self}: shuffling cards",'grey')
            while len(self.discard_pile):
                self.cards.append(self.discard_pile.pop(randint(0, len(self.discard_pile)-1)))
            # on coupe le tas?

        if len(self.cards) >= n:
            return list([self.cards.pop().draw(player) for _ in range(n)])
        elif len(self.cards) < n:
            r = n-len(self.cards)
            cards = [self.cards.pop() for _ in range(len(self.cards))]
            cards.extend( self.draw(r) )
            return list([c.draw(player) for c in cards])

        
    def discard(self, cards):
        self.discard_pile.extend([c for c in cards if c is not None])


class Card:
    def __init__(self, name, text, **kwargs ):
        #print(f"Card({name}, {kwargs})")
        self.name = name
        self.text = text
        self.uses_left = kwargs.get('uses_left', 0)
        try:
            # one of 'chance_jail_card', 'go_to_jail'
            self.action = kwargs['action']
        except KeyError:
            try:
                # TODO loop over kwargs.items(), red rid of GotAction
                for action in ('pay_bank', 'pay_each_player', 'street_repairs', 'advance', 'advanceToNearest', 'go_to'):
                    try:                setattr(self, action, kwargs[action])
                    except KeyError:    pass
                    else:               raise GotAction(self, action)
                raise ValueError(action)
            except GotAction:
                pass


    def __str__(self):
        return f"<Card:{self.name}>"

    def __repr__(self):
        return self.__str__()

    def draw(self, player):
        cprint(f"{player._name} drew {self} ({self.uses_left})", 'yellow')
        if not self.uses_left:
            # card is used immediately and returns to stack
            return self.use(player)
        else:
            player._player_cards.append(self)
            return None

    
    def use(self, player):
        try:
            getattr(player, self.action)( getattr(self, self.action) )
        except AttributeError:
            getattr(player, self.action)()

        if self.uses_left != 0:
            self.uses_left -= 1

        if self.uses_left == 0:
            return self

        # player keeps the card in hand
        return None

