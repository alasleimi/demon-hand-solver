from .card import *
import random

class Deck:
    __slots__ = ('cards',)
    
    def __init__(self, cards=None):
        # Internally, the deck stores only numbers representing each card
        if cards is None:
            self.cards = self._full_deck()
        else:
            self.cards = cards

    def _full_deck(self):
        total_cards = len(SUITS) * NUM_RANKS
        return list(range(total_cards))

    def _filter_deck(self, excluded_cards):
        # Use the card number for filtering rather than creating new Card objects
        excluded_numbers = {card.number for card in excluded_cards}
        return [num for num in self._full_deck() if num not in excluded_numbers]

    def shuffle(self):
        random.shuffle(self.cards)
    
    def external_draw(self, new_hand):
        # Remove cards from the internal deck based on their number
        new_hand_numbers = {card.number for card in new_hand}
        self.cards = [num for num in self.cards if num not in new_hand_numbers]
        if self.is_empty():
            self.reset(new_hand)

    def draw(self, n, hand=None):
        if hand is None:
            hand = []
        drawn = []
        for _ in range(n):
            if not self.cards:
                self.reset(hand + drawn)
            num = self.cards.pop()
            card = Card.from_number(num)
            # Determine if the card is critical
            card.critical = (random.random() < (3 / 100))
            drawn.append(card)
        return drawn

    def is_empty(self):
        return len(self.cards) == 0

    def reset(self, hand):
        self.cards = self._filter_deck(hand)
        self.shuffle()
