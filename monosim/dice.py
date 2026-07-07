#!/usr/bin/env python
# vim: noet ts=4 number

from synaptism.protocol import writeX

async def roll_dice_physical(d=6, n=2, player = None):
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


async def roll_dice_auto(d=6, n=2, player = None, game = None):
	""" Simulate the roll of two dice. Returns two int values between 1 and 6.

	:return: (tuple) two int values between 1 and 6 drawn from a uniform distribution.
	"""
	from random import randint

	tup = tuple([randint(1, d) for _ in range(n)])

	if player:
		if n > 1:
			writeX( player.writer, f"You rolled a {', '.join([str(t) for t in tup[:-1]])} and a {tup[-1]}".encode('utf-8') )
		else:
			writeX( player.writer, f"You rolled a {tup[0]}".encode('utf-8') )
	if game:
		if n > 1:
			await game.broadcast( f"{player._name} rolled a {', '.join([str(t) for t in tup[:-1]])} and a {tup[-1]}", NOT=(player, ) )
		else:
			await game.broadcast( f"{player._name} rolled a {tup[0]}", NOT=(player, ) )

	return tup


if __name__ == '__main__':
	from sys import argv
	
	try:
		D_TYPE = int(argv[1])
	except IndexError:
		D_TYPE = 6
	except ValueError:
		print(f"ERROR: cannot convert '{argv[1]}' to int (faces on each die)")
		exit(1)
	
	try:
		D_NUM = int(argv[2])
		raise NotImplementedError
	except IndexError:
		D_NUM = 2
	except ValueError:
		print(f"ERROR: cannot convert '{argv[2]}' to int (number of dice)")
		exit(1)
	
	"""
	def combine(i, v = 0):
		l = []
		if i == 0:
			return v
	
		for j in range(1,D_TYPE+1):
			combine(i-1, 
		l.append(v)
	
	l = combine[D_NUM)
	"""
	
	print(f"combinations of two {D_TYPE}-dice")
	l = []
	for i in range(1,D_TYPE+1):
		for j in range(1,D_TYPE+1):
				l.append(i+j)
				#print(f"{i}+{j}={i+j}")
	
	#print("combination occurence")
	r = {}
	for i in range(min(l),max(l)+1):
		r[i] = [l.count(i)]
		#print(f"{i:>2} {r[i]}")
	
	
	print("combination probability")
	s = sum([v[0] for v in r.values()])
	for k, v in r.items():
		r[k].append(v[0]/s)
		print(f"{k:>2} {v[0]/s*100:.3f}%")
