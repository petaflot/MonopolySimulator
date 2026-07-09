# vim: noet ts=4 number
CURRENCY_SYMBOL = "'000 $"
GO_AMOUNT = 200

AMOUNT_WIDTH = 11	  # width of numeric part, including sign

def format_amount(value: int | None, sign: str = "") -> str:
	"""
	Returns a fixed-width amount.

		0      -> "     +0'000 $"
		50     -> "    +50'000 $"
		120    -> "   +120'000 $"
		1234   -> " +1'234'000 $"
		None   -> "         ---"
	"""
	if value is None:
		return " " * (AMOUNT_WIDTH - 3) + "---"

	s = f"{value:,}".replace(",", "'")
	return f"{sign}{s}{CURRENCY_SYMBOL}".rjust(AMOUNT_WIDTH)
