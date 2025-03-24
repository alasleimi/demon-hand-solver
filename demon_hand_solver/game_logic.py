
from .count_call_util import count_calls
from .deck import *
from .card import RANK_ORDER
import math


# =============================================================================
# Action Definitions
# =============================================================================
class Action:
    __slots__ = ('type', 'card_indices')
    
    def __init__(self, type, card_indices):
        self.type = type  # "attack" or "discard"
        self.card_indices = card_indices

    def __repr__(self):
        return f"{self.type.capitalize()} using indices {self.card_indices}"


# =============================================================================
# Game State
# =============================================================================

class GameState:
    __slots__ = ('player_health', 'enemy_health', 'enemy_attack_power', 'enemy_attack_counter', 'enemy_base_counter',
                 'discard_count', 'enemy_base_counter', 'deck', 'hand',)
    
    def __init__(self, player_health=100, enemy_health=100, enemy_attack_power=10,
                 enemy_attack_counter=3, discard_count=3, enemy_base_counter=3,
                 deck=None, hand=None):
        self.player_health = player_health
        self.enemy_health = enemy_health
        self.enemy_attack_power = enemy_attack_power
        self.enemy_attack_counter = enemy_attack_counter
        self.discard_count = discard_count
        self.enemy_base_counter = enemy_base_counter
        if deck is None:
            self.deck = Deck()
            self.deck.shuffle()
        else:
            self.deck = deck
        if hand is None:
            self.hand = self.deck.draw(8)
        else:
            self.hand = hand

    @count_calls
    def clone(self):
        new_state = GameState(
            player_health=self.player_health,
            enemy_health=self.enemy_health,
            enemy_attack_power=self.enemy_attack_power,
            enemy_attack_counter=self.enemy_attack_counter,
            discard_count=self.discard_count,
            enemy_base_counter=self.enemy_base_counter,
            deck=Deck(self.deck.cards[:]),
            hand=self.hand[:]
        )
        return new_state

    def is_terminal(self):
        return self.enemy_health <= 0 or self.player_health <= 0

    def get_reward(self):
        if self.enemy_health <= 0:
            return self.player_health
        elif self.player_health <= 0:
            return -1000
        return 0

    def enemy_turn(self):
        if self.enemy_attack_counter <= 0:
            self.player_health -= self.enemy_attack_power
            self.enemy_attack_counter = self.enemy_base_counter

    def end_turn(self):
        if self.deck.is_empty():
            self.deck.reset(self.hand)
        if self.enemy_health <= 0:
            return
        if self.enemy_attack_counter <= 0:
            self.enemy_turn()


# =============================================================================
# Attack Combo Evaluation
# =============================================================================
def all_same_rank(cards):
    return all(card.rank == cards[0].rank for card in cards)

def all_same_suit(cards):
    return all(card.suit == cards[0].suit for card in cards)

def is_sequential(cards):
    sorted_cards = sorted(cards, key=lambda c: RANK_ORDER[c.rank])
    indices = [RANK_ORDER[c.rank] for c in sorted_cards]
    return all(indices[i] + 1 == indices[i+1] for i in range(len(indices) - 1))

def specific_demon_hand(cards):
    required = {"10", "command-1", "command-2", "command-3", "prime-0"}
    return {card.rank for card in cards} == required and all_same_suit(cards)

@count_calls
def valid_attack_combos(cards):
    n = len(cards)
    if n == 5:
        if specific_demon_hand(cards):
            return ("The Demon's Hand", 2000, sum(card_value(c) for c in cards))
        if is_sequential(cards) and all_same_suit(cards):
            return ("Marching Horde", 600, sum(card_value(c) for c in cards))
        if all_same_suit(cards):
            return ("Horde", 125, sum(card_value(c) for c in cards))
        if is_sequential(cards):
            return ("March", 100, sum(card_value(c) for c in cards))
        ranks = {}
        for card in cards:
            ranks[card.rank] = ranks.get(card.rank, 0) + 1
        if sorted(ranks.values()) == [2, 3]:
            return ("Grand Warhost", 175, sum(card_value(c) for c in cards))
    if n == 4:
        ranks = {}
        for card in cards:
            ranks[card.rank] = ranks.get(card.rank, 0) + 1
        if sorted(ranks.values()) == [2, 2] and len(ranks) == 2:
            return ("Dyad Set", 40, sum(card_value(c) for c in cards))
        if all_same_rank(cards):
            return ("Tetrad", 400, sum(card_value(c) for c in cards))
    if n == 3:
        if all_same_rank(cards):
            return ("Triad", 80, sum(card_value(c) for c in cards))
    if n == 2:
        if all_same_rank(cards):
            return ("Dyad", 20, sum(card_value(c) for c in cards))
    highest_card = max(cards, key=card_value)
    return ("Solo", 10, card_value(highest_card))