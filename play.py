#!/usr/bin/env python
from monosim.board import game_board, get_community_chest_cards, get_chance_cards
from monosim.bank import Bank
from monosim.player import Player
from monosim.custom_exceptions import InsufficientFundsAvailable

if __name__ == '__main__':
    import random
    from os import system
    clear = lambda: system('clear')
    from time import sleep

    from sys import argv
    try:
        player_count = int(argv[1])
    except IndexError:
        player_count = 2

    for seed in range(0, 10000):
        random.seed(seed)
        bank = Bank()
        community_cards_deck = get_community_chest_cards()
        chance_cards_deck = get_chance_cards()

        list_players = list([ Player(f"Player{i}", i, bank, game_board, community_cards_deck, chance_cards_deck) for i in range(player_count) ])

        for player in list_players:
            player.meet_other_players(list_players)


        try:
            idx_count = 0
            while not any([player.has_lost() for player in list_players]) and idx_count < 2000:
                #clear()
                for player in list_players:
                    print(player.get_print_state())
                    player.play()
                    #clear()
                    print(player.get_print_state(),end='\n\n')
                sleep(.01)
                idx_count += 1
        except (InsufficientFundsAvailable, Exception) as e:
            print(e)
            raise
            if input("play again? ").lower() not in ('y','yes'):
                break
