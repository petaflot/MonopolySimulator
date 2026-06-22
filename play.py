#!/usr/bin/env python
from monosim.player import Player
from monosim.bank import Bank
from monosim.board import get_board, get_roads, get_properties, get_community_chest_cards

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
        list_board, dict_roads = get_board(),  get_roads()
        dict_properties = get_properties()
        community_cards_deck = list(get_community_chest_cards().keys())

        list_players = list([ Player(f"Player{i}", i, bank, list_board, dict_roads, dict_properties, community_cards_deck) for i in range(player_count) ])

        for player in list_players:
            player.meet_other_players(list_players)

        idx_count = 0
        while not any([player.has_lost() for player in list_players]) and idx_count < 2000:
            #clear()
            for player in list_players:
                print(player.get_print_state())
                player.play(interactive=True)
                #clear()
                print(player.get_print_state(),end='\n\n')
            sleep(.01)
            idx_count += 1
