from .count_call_util import count_calls

# =============================================================================
# Global Card Definitions and Bitmask Mapping
# =============================================================================
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10",
         "command-1", "command-2", "command-3", "prime-0"]
SUITS = ["Moon", "Fire", "Sun", "Stone"]
RANK_ORDER = {rank: i for i, rank in enumerate(RANKS)}
NUM_RANKS = len(RANKS)
SUIT_INDEX = {suit: i for i, suit in enumerate(SUITS)}
RANKS_INDEX = {rank: i for i, rank in enumerate(RANKS)}

def compute_bitmask(cards):
    """Compute an integer bitmask for a list of Card objects."""
    mask = 0
    for card in cards:
        mask |= 1 << card.number
    return mask


class Card:
    __slots__ = ('suit', 'rank', 'critical', 'number')

    def __init__(self, suit, rank, critical=False):
        self.suit = suit
        self.rank = rank
        # Calculate a unique number for each card based on suit and rank indices
        self.number = SUIT_INDEX[suit] * NUM_RANKS + RANKS_INDEX[rank]
        self.critical = critical

    @classmethod
    def from_number(cls, number, critical=False):
        suit = SUITS[number // NUM_RANKS]
        rank = RANKS[number % NUM_RANKS]
        return cls(suit, rank, critical)

    def __repr__(self):
        crit = " (Critical)" if self.critical else ""
        return f"{self.rank} of {self.suit}{crit}"
    
@count_calls
def card_value(card):
    rank = card.number % NUM_RANKS
    if rank == NUM_RANKS - 1:
        return 11
    return min(rank + 2, 10)