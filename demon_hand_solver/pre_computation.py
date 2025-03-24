import importlib
from itertools import combinations
import os
import pickle
from .card import SUITS, RANKS
from .deck import *
from .game_logic import *
from .count_call_util import count_calls
from importlib.resources import files


def load_pickle_file(filename):
    # Try loading from the 'DATA' package using importlib
    try:
        package_name = __package__ or '__main__' 
        data_dir = importlib.resources.files(package_name).joinpath('DATA')
        with data_dir.joinpath(filename).open('rb') as f:
            return pickle.load(f)
    except (ModuleNotFoundError, FileNotFoundError, AttributeError) as e:
        pass  # Try the next method

    # Try loading from local 'DATA' directory
    try:
        local_path = os.path.join('DATA', filename)
        with open(local_path, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return None
    
def save_pickle_file(obj, filename):
    # Try saving to the DATA folder inside the current package
    try:
        package_name = __package__ or '__main__'  # fallback if not part of a package
        data_dir = importlib.resources.files(package_name).joinpath('DATA')
        os.makedirs(data_dir, exist_ok=True)
        with open(data_dir / filename, 'wb') as f:
            pickle.dump(obj, f)
            return True
    except Exception:
        pass  # Try the next method

    # Fallback: save to local DATA folder in current directory
    try:
        os.makedirs('DATA', exist_ok=True)
        with open(os.path.join('DATA', filename), 'wb') as f:
            pickle.dump(obj, f)
            return True
    except Exception:
        return False

# =============================================================================
# Global Cache for Combination Indices
# =============================================================================

COMBO_CACHE = {}

@count_calls
def get_combo_indices(n):
    """Return all nonempty combinations of indices (up to min(n, 5)) with each combination's indices in descending order."""
    if n in COMBO_CACHE:
        return COMBO_CACHE[n]
    else:
        max_cards = min(5, n)
        combos = [
            tuple(reversed(combo))
            for r in range(1, max_cards + 1)
            for combo in combinations(range(n), r)
        ]
        COMBO_CACHE[n] = combos
        return combos



# =============================================================================
# Precomputed Attack Lookup (ignoring critical flags)
# =============================================================================
# This table maps:
#   key = bitmask representing a nonempty subset of cards
# to (combo_name, base_damage) where base_damage = (base + bonus) as computed by valid_attack_combos.
PRECOMPUTED_ATTACK_LOOKUP = {}

def precompute_attack_lookup():
    global PRECOMPUTED_ATTACK_LOOKUP
    if (lookup := load_pickle_file("precomputed_attack_lookup.pkl")):
        PRECOMPUTED_ATTACK_LOOKUP = lookup
        return
    ALL_CARDS = [(rank, suit) for suit in SUITS for rank in RANKS]
    total = 0
    for r in range(1, 6):
        for comb in combinations(ALL_CARDS, r):
            # Create dummy Card objects with critical=False.
            dummy_cards = [Card(suit, rank, critical=False) for rank, suit in comb]
            key = compute_bitmask(dummy_cards)
            combo_name, base, bonus = valid_attack_combos(dummy_cards)
            PRECOMPUTED_ATTACK_LOOKUP[key] = (combo_name, base + bonus)
            total += 1

    save_pickle_file(PRECOMPUTED_ATTACK_LOOKUP, "precomputed_attack_lookup.pkl")
    print(f"Precomputed attack lookup for {total} combinations and saved them.")

# =============================================================================
# Precomputed Best Attack Lookup (ignoring critical flags)
# =============================================================================
# This table maps:
#   key = bitmask representing an attack action (subset of cards, size 1–5)
# to the best base damage (damage value only)
BEST_ATTACK_LOOKUP = {}

def precompute_best_attack_lookup():

    global BEST_ATTACK_LOOKUP
    if (lookup := load_pickle_file("best_attack_lookup.pkl")):
        BEST_ATTACK_LOOKUP = lookup
        print("Loaded precomputed best attack lookup")
        return
    print("Precomputing best attack lookup")
    if not PRECOMPUTED_ATTACK_LOOKUP:
        precompute_attack_lookup()
    ALL_CARDS = [(rank, suit) for suit in SUITS for rank in RANKS]
    total = 0
    for r in range(1, 6):
        for X in combinations(ALL_CARDS, r):
            # Build dummy Card objects for X.
            dummy_cards_X = [Card(suit, rank, critical=False) for rank, suit in X]
            X_key = compute_bitmask(dummy_cards_X)
            best_damage = -float("inf")
            # For each nonempty subset Y of X.
            for s in range(1, len(dummy_cards_X) + 1):
                for Y in combinations(dummy_cards_X, s):
                    Y_key = compute_bitmask(Y)
                    if Y_key in PRECOMPUTED_ATTACK_LOOKUP:
                        _, base_damage = PRECOMPUTED_ATTACK_LOOKUP[Y_key]
                        if base_damage > best_damage:
                            best_damage = base_damage
            BEST_ATTACK_LOOKUP[X_key] = best_damage
            total += 1

    save_pickle_file(BEST_ATTACK_LOOKUP, "best_attack_lookup.pkl")
    print(f"Precomputed best attack lookup for {total} combinations and saved them")


# =============================================================================
MAX_HAND_SIZE = 10

# Precompute immutable actions based on hand length.
PRECOMPUTED_ATTACK_ACTIONS = {}
PRECOMPUTED_DISCARD_ACTIONS = {}

for hand_length in range(1, MAX_HAND_SIZE + 1):
    combos = get_combo_indices(hand_length)
    PRECOMPUTED_ATTACK_ACTIONS[hand_length] = [Action("attack", list(combo)) for combo in combos]
    PRECOMPUTED_DISCARD_ACTIONS[hand_length] = [Action("discard", list(combo)) for combo in combos]


def precompute_tables(args = None):
    if not BEST_ATTACK_LOOKUP:
        precompute_best_attack_lookup()

# -----------------------------------------------------------------------------
#  compute_best_attack: only returns the damage (with critical bonus) using the table
# -----------------------------------------------------------------------------
@count_calls
def compute_best_attack(cards):
    """
    Given a list of Card objects (which may have critical flags),
    build a bitmask key (ignoring critical flags), look up the precomputed best damage,
    then add the critical bonus from every card in the attack action.
    """
    key = compute_bitmask(cards)
    base_damage = BEST_ATTACK_LOOKUP[key]
    num_crit = sum(1 for card in cards if card.critical)
    final_damage = base_damage * (1 + 0.25 * num_crit)
    return final_damage

@count_calls
def apply_attack(state, action):
    played_cards = [state.hand[i] for i in action.card_indices]
    damage = compute_best_attack(played_cards)
    state.enemy_health -= damage
    # Remove cards from hand in reverse order to avoid index shifting.
    for index in sorted(action.card_indices, reverse=True):
        state.hand.pop(index)
    new_cards = state.deck.draw(len(action.card_indices), state.hand)
    state.hand.extend(new_cards)
    state.enemy_attack_counter -= 1
    state.end_turn()
    return damage

@count_calls
def apply_discard(state, action):
    if state.discard_count <= 0:
        return False
    for index in sorted(action.card_indices, reverse=True):
        state.hand.pop(index)
    new_cards = state.deck.draw(len(action.card_indices), state.hand)
    state.hand.extend(new_cards)
    state.discard_count -= 1
    state.end_turn()
    return True

@count_calls
def get_legal_count(state):
    n = len(state.hand)
    ans =  len(PRECOMPUTED_ATTACK_ACTIONS.get(n, []))
    if state.discard_count > 0:
        ans += len(PRECOMPUTED_DISCARD_ACTIONS.get(n, []))
    return ans