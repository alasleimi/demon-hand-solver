import random
import math
import time

import multiprocessing
from .count_call_util import count_calls
from .game_logic import *
from .pre_computation import (apply_attack, apply_discard, get_legal_count,
                             PRECOMPUTED_ATTACK_ACTIONS,PRECOMPUTED_DISCARD_ACTIONS,
                             compute_best_attack,
                             precompute_tables)



# =============================================================================
# Monte Carlo Tree Search (MCTS) Agent with Time Limit and Multiprocessing
# =============================================================================
class MCTSNode:
    __slots__ = ('state', 'parent', 'action', 'children', 'visits', 'value', 'untried_actions_count')
    
    def __init__(self, state, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.visits = 0
        self.value = 0.0
        if state.is_terminal():
            self.untried_actions_count = 0
        else:
            self.untried_actions_count = get_legal_count(state)

    def is_fully_expanded(self):
        return self.untried_actions_count == 0

    @count_calls
    def best_child(self, c_param=1.4):
        unvisited = [child for child in self.children if child.visits == 0]
        if unvisited:
            return random.choice(unvisited)
        best = None
        best_score = -float('inf')
        log_parent_visits = math.log(self.visits)
        for child in self.children:
            score = child.value  + c_param * math.sqrt(2 * log_parent_visits / child.visits)
            if score > best_score:
                best_score = score
                best = child
        return best

    @count_calls
    def expand(self):
        if self.untried_actions_count <= 0:
            return
        attacks = PRECOMPUTED_ATTACK_ACTIONS.get(len(self.state.hand), [])
        discards = PRECOMPUTED_DISCARD_ACTIONS.get(len(self.state.hand), [])
        if self.untried_actions_count >= len(attacks):
            action = discards[self.untried_actions_count - len(attacks) - 1]
        else:
            action = attacks[self.untried_actions_count - 1]
        next_state = self.state.clone()
        if action.type == "attack":
            apply_attack(next_state, action)
        elif action.type == "discard":
            apply_discard(next_state, action)
        child_node = MCTSNode(next_state, parent=self, action=action)
        self.children.append(child_node)
        self.untried_actions_count -= 1 
        return child_node

def mcts_worker(args):
    root_state, soft_limit = args
    # Ensure that the precomputed lookup tables are loaded in this worker.
    precompute_tables()
    # Each worker uses a determinized clone of the state.
    determinized_state = root_state.clone()
    determinized_state.deck.shuffle()
    root_node = MCTSNode(determinized_state)
    
    start_time = time.time()

    while time.time() - start_time < soft_limit or not root_node.is_fully_expanded():
        node = root_node
        # Selection: traverse until a node with untried actions or terminal state.
        while (not node.state.is_terminal()) and node.is_fully_expanded() and node.children:
            node = node.best_child()
        # Expansion:
        if not node.state.is_terminal() and node.untried_actions_count > 0: 
            node = node.expand()
        # Simulation (rollout):
        rollout_state = node.state.clone()
        n_hand = -1
        actions = []
        discards = []
        while not rollout_state.is_terminal():
            if n_hand != len(rollout_state.hand):
                n_hand = len(rollout_state.hand)
                actions = PRECOMPUTED_ATTACK_ACTIONS.get(n_hand, [])
                discards = PRECOMPUTED_DISCARD_ACTIONS.get(n_hand, [])
            if n_hand == 0:
                break
            winning_action = None
            for action in reversed(actions): 
                if len(action.card_indices) < min(n_hand, 5): 
                    break
                played_cards = [rollout_state.hand[i] for i in action.card_indices]
                damage = compute_best_attack(played_cards)
                if rollout_state.enemy_health - damage <= 0:
                    winning_action = action
                    break
                    
            if winning_action is None:
                m = 2 if rollout_state.discard_count > 0 else 1
                choice = random.randint(0, m * len(actions) - 1)
                if choice < len(actions):
                    apply_attack(rollout_state, actions[choice])
                else:
                    apply_discard(rollout_state, discards[choice - len(actions)])
            else:
                apply_attack(rollout_state, winning_action)

        reward = rollout_state.get_reward()

        # Backpropagation
        temp_node = node
        while temp_node is not None:
            temp_node.visits += 1
            temp_node.value = max(reward, temp_node.value)
            temp_node = temp_node.parent

    # Aggregate statistics from this determinization run.
    aggregated_moves = {}
    for child in root_node.children:
        key = repr(child.action)
        total_val, total_visits, _ = aggregated_moves.get(key, (0, 0, child.action))
        aggregated_moves[key] = (total_val + child.value, total_visits + 1, child.action)
    return aggregated_moves

def mcts(pool, root_state, soft_limit=30, num_determinizations=50, ):
    """
    Run multiple independent MCTS determinization simulations in parallel,
    using a pool of processes (one per CPU core).
    After all runs, aggregate the statistics from the root node's children and
    choose the best move.
    """
    start = time.time()
    num_workers = multiprocessing.cpu_count()
    tasks = [(root_state, 0.75 * soft_limit * (num_workers / num_determinizations)) for _ in range(num_determinizations)]
    
    results = pool.map(mcts_worker, tasks)
    
    aggregated_moves = {}
    for agg in results:
        for key, (total_val, total_visits, action) in agg.items():
            if key in aggregated_moves:
                prev_val, prev_visits, _ = aggregated_moves[key]
                aggregated_moves[key] = (prev_val + total_val, prev_visits + total_visits, action)
            else:
                aggregated_moves[key] = (total_val, total_visits, action)
    
    best_action = None
    best_avg = -float("inf")
    for key, (total_value, total_visits, action) in aggregated_moves.items():
        avg = total_value / total_visits if total_visits > 0 else -float("inf")
        if avg > best_avg:
            best_avg = avg
            best_action = action
        elif avg == best_avg and best_action.type == "discard":
            best_action = action
    end = time.time() - start
    print(end)
    return best_action, best_avg

# =============================================================================

