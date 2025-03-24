from enum import Enum
import multiprocessing
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from .demon_hand_mcts import (
    Card, Deck, GameState, mcts, compute_best_attack,
    precompute_tables, RANKS, SUITS
)
from .ocr_hand import get_hands_ocr  # Import the OCR function

# Global variables
persistent_deck = Deck()
prev_hand = None
suggested_action = None

# Helper function to run OCR in a separate process
def ocr_process(conn):
    """
    Runs the get_hands_ocr function and sends the result via a connection.
    """
    try:
        result = get_hands_ocr()
        conn.send(result)
    except Exception as e:
        conn.send(e)
    finally:
        conn.close()

class STATE(Enum):
    IDLE = 0    
    RUNNING = 1
    FINISHED = 2
    FAILED = 3

class GameApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("The Demon Hand Solver - GUI Interface")
        self.geometry("900x700")
        num_workers = multiprocessing.cpu_count() 
        self.pool = multiprocessing.Pool(processes=num_workers)
        
        # Variables for game state inputs
        self.player_health_var = tk.StringVar(value="100")
        self.enemy_health_var = tk.StringVar(value="200")
        self.enemy_attack_power_var = tk.StringVar(value="3")
        self.enemy_attack_counter_var = tk.StringVar(value="2")
        self.discard_count_var = tk.StringVar(value="3")
        self.enemy_base_counter_var = tk.StringVar(value="3")

        # Deck size variable (display "N/A" if no deck yet)
        self.deck_size_var = tk.StringVar(value=f"{int(len(persistent_deck.cards))}")

        self.time_limit = 30

        # OCR state variables
        self.ocr_running = False
        self.ocr_cancelled = False
        self.ocr_process_obj = None  # To hold the OCR process reference

        self.mcts_state = STATE.IDLE

        # List to hold current hand (list of Card objects)
        self.current_hand = []  # our model for the hand
        # List to hold row dictionaries for UI elements of each card in hand.
        self.card_rows = []

        # --------------------------
        # Main Window Layout
        # --------------------------
        self.columnconfigure(0, weight=1, uniform="half")
        self.columnconfigure(1, weight=1, uniform="half")
        self.rowconfigure(0, weight=1)

        self.left_frame = ttk.Frame(self)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.right_frame = ttk.Frame(self)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # --------------------------
        # Left Frame Layout
        # --------------------------
        self.left_frame.rowconfigure(0, weight=1)  # Hand frame can expand
        self.left_frame.rowconfigure(1, weight=0)  # Game state does not expand
        self.left_frame.columnconfigure(0, weight=1)

        self.create_hand_frame(self.left_frame)       # top
        self.create_game_state_frame(self.left_frame)   # bottom

        # --------------------------
        # Right Frame Layout
        # --------------------------
        self.right_frame.rowconfigure(0, weight=0)
        self.right_frame.rowconfigure(1, weight=1)  # Console expands
        self.right_frame.columnconfigure(0, weight=1)

        self.create_action_frame(self.right_frame)
        self.create_console_frame(self.right_frame)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
       
        # Store current game state
        self.game_state = None
        self.deck = None  # persistent deck is maintained globally
         # Precompute tables in background
        threading.Thread(target=self.threaded_precompute_tables, daemon=True).start()

    def on_close(self):
        try:
            if self.pool:
                self.pool.close()
                self.pool.terminate()
                self.pool.join()
                self.log("Multiprocessing pool has been terminated.")
        except Exception as e:
            self.log(f"Error shutting down pool: {e}")
        finally:
            self.destroy()

    def threaded_precompute_tables(self):
        self.log("Precomputing or loading game tables in the background.\n"
                "This may take a while during the first run of the program...")
        precompute_tables()
        self.pool.map(precompute_tables, [None]*multiprocessing.cpu_count())
        self.log("Precomputation of tables complete.")

    def create_hand_frame(self, parent):
        """Hand (Cards) at the top of the left column, with OCR and manual edit buttons."""
        self.hand_frame = ttk.LabelFrame(parent, text="Hand (Cards)")
        self.hand_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # OCR button at the very top (row=0)
        self.ocr_button = ttk.Button(self.hand_frame, text="Run OCR", command=self.start_threaded_ocr)
        self.ocr_button.grid(row=0, column=0, columnspan=5, sticky="ew", padx=5, pady=(5, 10))

        # Header row (row=1)
        headers = ["Index", "Rank", "Suit", "Critical", "Action"]
        for col, text in enumerate(headers):
            lbl = ttk.Label(self.hand_frame, text=text, font=("TkDefaultFont", 10, "bold"))
            lbl.grid(row=1, column=col, padx=5, pady=3)

        # Let columns expand equally
        for i in range(5):
            self.hand_frame.columnconfigure(i, weight=1)
        self.hand_frame.columnconfigure(1, weight=4)  # Rank column expands more
        # Add "Add Card" button below the hand list.
        self.add_card_button = ttk.Button(self.hand_frame, text="Add Card", command=self.open_add_card_dialog)
        self.add_card_button.grid(row=100, column=0, columnspan=5, sticky="ew", padx=5, pady=5)

    def create_game_state_frame(self, parent):
        """Game State Inputs at the bottom of the left column."""
        frame = ttk.LabelFrame(parent, text="Game State Inputs")
        frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # Make a simple two-column layout: one column for labels, one for entries.
        for i in range(9):
            frame.rowconfigure(i, weight=0)
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)

        inputs = [
            ("Player Health",        self.player_health_var),
            ("Enemy Health",         self.enemy_health_var),
            ("Enemy Attack Power",   self.enemy_attack_power_var),
            ("Enemy  Attack Counter", self.enemy_attack_counter_var),
            ("Available Discards",   self.discard_count_var),
            ("Enemy base Attack Counter",         self.enemy_base_counter_var),
        ]

        # Create label/entry for each input
        for i, (label_text, var) in enumerate(inputs):
            lbl = ttk.Label(frame, text=label_text, font=("TkDefaultFont", 9))
            lbl.grid(row=i, column=0, padx=5, pady=2, sticky="w")

            ent = ttk.Entry(frame, width=12, textvariable=var, font=("TkDefaultFont", 9))
            ent.grid(row=i, column=1, padx=5, pady=2, sticky="w")

        # Deck Size row (row=6)
        deck_lbl = ttk.Label(frame, text="Deck Size", font=("TkDefaultFont", 9))
        deck_lbl.grid(row=6, column=0, padx=5, pady=2, sticky="w")

        deck_val_lbl = ttk.Label(frame, textvariable=self.deck_size_var, font=("TkDefaultFont", 9))
        deck_val_lbl.grid(row=6, column=1, padx=5, pady=2, sticky="w")

        # Reset Game button (row=7)
        reset_button = ttk.Button(frame, text="Reset Game", command=self.reset_game)
        reset_button.grid(row=7, column=0, padx=5, pady=5, sticky="we")

        # Edit Deck button (row=7, column=1)
        edit_deck_button = ttk.Button(frame, text="Edit Deck", command=self.open_deck_editor)
        edit_deck_button.grid(row=7, column=1, padx=5, pady=5, sticky="we")

    def create_action_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Actions")
        frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        find_button = ttk.Button(frame, text="Find Next Action", command=self.start_threaded_mcts)
        find_button.grid(row=0, column=0, padx=5, pady=5, sticky="we")

        push_button = ttk.Button(frame, text="Push Next Action", command=self.push_next_action)
        push_button.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        self.suggestion_text = tk.Text(frame, height=6, width=80, state="disabled", wrap="word")
        self.suggestion_text.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        frame.rowconfigure(1, weight=1)

        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(frame, maximum=self.time_limit, variable=self.progress_var)
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="we")

    def create_console_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Console / Status")
        frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.console_text = tk.Text(frame, height=10, width=100, state="disabled", wrap="word")
        self.console_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    def log(self, message):
        self.console_text.config(state="normal")
        self.console_text.insert("end", message + "\n")
        self.console_text.see("end")
        self.console_text.config(state="disabled")

    # --------------------------------------------------------------------------
    # OCR methods with Run/Cancel toggling using a separate process
    # --------------------------------------------------------------------------
    def start_threaded_ocr(self):
        """
        Toggles between starting OCR (Run OCR) and canceling it (Cancel OCR).
        """
        if not self.ocr_running:
            # Start OCR
            self.ocr_running = True
            self.ocr_cancelled = False
            self.ocr_button.config(text="Cancel OCR")
            self.log("Navigate to the game client and use numpad-0 to capture a screenshot")
            threading.Thread(target=self.run_ocr, daemon=True).start()
        else:
            # Cancel OCR
            self.ocr_cancelled = True
            self.log("OCR canceled by user.")

    def run_ocr(self):
        """
        Runs OCR in a separate process so that it can be terminated if needed.
        """
        parent_conn, child_conn = multiprocessing.Pipe()
        self.ocr_process_obj = multiprocessing.Process(target=ocr_process, args=(child_conn,))
        self.ocr_process_obj.start()

        # Wait in a loop, checking for cancellation
        while self.ocr_process_obj.is_alive():
            if self.ocr_cancelled:
                self.ocr_process_obj.terminate()
                self.log("OCR process terminated due to cancellation.")
                self.after(0, self.finish_ocr)
                return
            time.sleep(0.1)

        # Process finished naturally; get the result
        if parent_conn.poll():
            ocr_result = parent_conn.recv()
        else:
            ocr_result = None

        self.ocr_process_obj.join()

        if self.ocr_cancelled or ocr_result is None:
            self.after(0, self.finish_ocr)
            return

        if isinstance(ocr_result, Exception):
            self.after(0, lambda: messagebox.showerror("OCR failed (make sure you're in the game):", str(ocr_result)))
            self.after(0, self.finish_ocr)
            return

        # Convert OCR result into Card objects and update our hand.
        new_hand = []
        suit_mapping = {"Flame": "Fire"}
        for suit, rank in ocr_result:
            mapped_suit = suit_mapping.get(suit, suit)
            new_hand.append(Card(mapped_suit, rank))
        self.current_hand = new_hand
        # Refresh the hand UI on the main thread
        self.after(0, self.refresh_hand_ui)
        self.after(0, lambda: self.log(
            "OCR-detected hand:\n" +
            "\n".join(f"{i+1}. {card}" for i, card in enumerate(self.current_hand)) +
            "\nThe deck has not been updated yet.\n"
            "Fix any errors then click 'Edit Deck' or 'Find Next Action'."
        ))
        self.after(0, self.finish_ocr)

    def finish_ocr(self):
        """
        Resets the OCR button/text and internal flags once OCR is done or canceled.
        """
        self.ocr_running = False
        self.ocr_cancelled = False
        self.ocr_button.config(text="Run OCR")
        self.log("Finished OCR.")

    # --------------------------------------------------------------------------
    # Hand UI methods (manual add / remove)
    # --------------------------------------------------------------------------
    def refresh_hand_ui(self):
        """Clears and repopulates the hand_frame with rows based on self.current_hand."""
        # Remove all rows except the first two (OCR button and headers) and the add button (row 100)
        for widget in self.hand_frame.winfo_children():
            grid_row = widget.grid_info().get("row", 0)
            if grid_row not in (0, 1, 100):
                widget.destroy()
        self.card_rows.clear()
        for i, card in enumerate(self.current_hand):
            row_dict = {}
            row_index = i + 2  # start after headers

            # Index label
            idx_lbl = ttk.Label(self.hand_frame, text=str(i))
            idx_lbl.grid(row=row_index, column=0, padx=5, pady=2, sticky="nsew")
            row_dict["index_label"] = idx_lbl

            # Rank entry 
            rank_var = tk.StringVar(value=card.rank)
            rank_entry = ttk.Entry(self.hand_frame, textvariable=rank_var, width=8)
            rank_entry.grid(row=row_index, column=1, padx=5, pady=2, sticky="nsew")
            row_dict["rank_var"] = rank_var

            # Suit option menu 
            suit_var = tk.StringVar(value=card.suit)
            suit_menu = ttk.OptionMenu(self.hand_frame, suit_var, card.suit, *SUITS)
            suit_menu.config()
            suit_menu.grid(row=row_index, column=2, padx=5, pady=2, sticky="nsew")
            row_dict["suit_var"] = suit_var

            # Critical check 
            crit_var = tk.BooleanVar(value=card.critical)
            crit_check = ttk.Checkbutton(self.hand_frame, variable=crit_var)
            crit_check.grid(row=row_index, column=3, padx=5, pady=2, sticky="nsew")
            row_dict["crit_var"] = crit_var

            # Remove button for the card
            remove_button = ttk.Button(self.hand_frame, text="Remove", 
                                       command=lambda idx=i: self.remove_card(idx))
            remove_button.grid(row=row_index, column=4, padx=5, pady=2, sticky="nsew")
            row_dict["remove_button"] = remove_button

            self.card_rows.append(row_dict)
        # Update "Add Card" button state based on hand size
        if len(self.current_hand) >= 10:
            self.add_card_button.config(state="disabled")
        else:
            self.add_card_button.config(state="normal")

    def open_add_card_dialog(self):
        """Opens a dialog for the user to add a card manually."""
        if len(self.current_hand) >= 10:
            messagebox.showerror("Hand Full", "You cannot have more than 10 cards in hand.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Add Card")
        dialog.grab_set()  # modal

        ttk.Label(dialog, text="Rank:").grid(row=0, column=0, padx=5, pady=5)
        rank_var = tk.StringVar(value=RANKS[0])
        rank_menu = ttk.OptionMenu(dialog, rank_var, RANKS[0], *RANKS)
        rank_menu.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(dialog, text="Suit:").grid(row=1, column=0, padx=5, pady=5)
        suit_var = tk.StringVar(value=SUITS[0])
        suit_menu = ttk.OptionMenu(dialog, suit_var, SUITS[0], *SUITS)
        suit_menu.grid(row=1, column=1, padx=5, pady=5)

        crit_var = tk.BooleanVar(value=False)
        crit_check = ttk.Checkbutton(dialog, text="Critical", variable=crit_var)
        crit_check.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

        def add_card():
            # Create a temporary card to check uniqueness (critical does not affect card.number)
            new_card = Card(suit_var.get(), rank_var.get(), crit_var.get())
            # Check for duplicate (by card.number)
            for card in self.current_hand:
                if card.number == new_card.number:
                    messagebox.showerror("Duplicate Card", "This card is already in your hand.")
                    return
            self.current_hand.append(new_card)
            self.refresh_hand_ui()
            dialog.destroy()

        add_button = ttk.Button(dialog, text="Add", command=add_card)
        add_button.grid(row=3, column=0, padx=5, pady=5)
        cancel_button = ttk.Button(dialog, text="Cancel", command=dialog.destroy)
        cancel_button.grid(row=3, column=1, padx=5, pady=5)

    def remove_card(self, index):
        """Removes a card from the hand given its index."""
        if 0 <= index < len(self.current_hand):
            del self.current_hand[index]
            self.refresh_hand_ui()

    def read_hand_from_ui(self):
        """Rebuilds the hand from our model."""
        return self.current_hand

    # --------------------------------------------------------------------------
    # MCTS / Action methods
    # --------------------------------------------------------------------------
    def start_threaded_mcts(self):
        if STATE.RUNNING == self.mcts_state:
            return
        self.mcts_state = STATE.RUNNING    
        self.reset_progress()
        threading.Thread(target=self.find_next_action, daemon=True).start()
        self.update_progress()

    def reset_progress(self):
        self.progress_var.set(0)

    def update_progress(self):
        current = self.progress_var.get()
        if self.mcts_state == STATE.FAILED:
            self.reset_progress()
            return  
        if current < self.time_limit:
            if (current + 1 < self.time_limit and self.mcts_state == STATE.RUNNING) or self.mcts_state == STATE.FINISHED:
                self.progress_var.set(current + 1) 
            self.after(1000, self.update_progress)
      
    def find_next_action(self):
        global persistent_deck, prev_hand, suggested_action

        new_hand = self.read_hand_from_ui()
        if len(new_hand) == 0:
            self.after(0, lambda: messagebox.showerror(
                "Input Error", "hand must not be empty use OCR or fill manually"))
            self.mcts_state = STATE.FAILED
            return
            
        try:
            player_health = int(self.player_health_var.get())
            enemy_health = int(self.enemy_health_var.get())
            enemy_attack_power = int(self.enemy_attack_power_var.get())
            enemy_attack_counter = int(self.enemy_attack_counter_var.get())
            discard_count = int(self.discard_count_var.get())
            enemy_base_counter = int(self.enemy_base_counter_var.get())
        except ValueError:
            self.after(0, lambda: messagebox.showerror(
                "Input Error", "Ensure that game state inputs are valid integers."))
            self.mcts_state = STATE.FAILED
            return
        
        if persistent_deck is None:
            persistent_deck = Deck()
            persistent_deck.shuffle()

        persistent_deck.external_draw(new_hand)

        if persistent_deck is not None:
            self.deck_size_var.set(str(len(persistent_deck.cards)))
        else:
            self.deck_size_var.set("N/A")

        self.game_state = GameState(
            player_health=player_health,
            enemy_health=enemy_health,
            enemy_attack_power=enemy_attack_power,
            enemy_attack_counter=enemy_attack_counter,
            discard_count=discard_count,
            enemy_base_counter=enemy_base_counter,
            deck=persistent_deck,
            hand=new_hand
        )
        self.log(f"persistent_deck size: {len(persistent_deck.cards)}")
        self.log("Running MCTS to determine the next best action...")
        best_node_action, reward = mcts(self.pool, self.game_state, self.time_limit)
        suggested_action = best_node_action
        
        suggestion_info = ""
        if suggested_action.type == "attack":
            played_cards = [self.game_state.hand[i] for i in suggested_action.card_indices]
            expected_damage = compute_best_attack(played_cards)
            suggestion_info += "Suggested Move: ATTACK\n"
            suggestion_info += f"Card indices to play: {suggested_action.card_indices}\n"
            suggestion_info += "Cards: " + ", ".join(str(card) for card in played_cards) + "\n"
            suggestion_info += f"Expected Damage: {expected_damage:.2f}\n"
        else:
            discard_cards = [self.game_state.hand[i] for i in suggested_action.card_indices]
            suggestion_info += "Suggested Move: DISCARD\n"
            suggestion_info += f"Card indices to discard: {suggested_action.card_indices}\n"
            suggestion_info += "Cards: " + ", ".join(str(card) for card in discard_cards) + "\n"

        suggestion_info += f"Expected Reward: {reward:.2f}\n"
        
        self.after(0, self.update_suggestion_ui, suggestion_info)
        self.mcts_state = STATE.FINISHED

    def update_suggestion_ui(self, suggestion_info):
        self.suggestion_text.config(state="normal")
        self.suggestion_text.delete("1.0", tk.END)
        self.suggestion_text.insert(tk.END, suggestion_info)
        self.suggestion_text.config(state="disabled")

    def push_next_action(self):
        global suggested_action, prev_hand
        if suggested_action is None:
            messagebox.showerror("Error", "No action has been suggested. Click 'Find Next Action' first.")
            return

        new_state = self.game_state.clone()
        new_state.deck = self.game_state.deck
        new_state.hand = self.game_state.hand

        if suggested_action.type == "attack":
            played_cards = [new_state.hand[i] for i in suggested_action.card_indices]
            damage = compute_best_attack(played_cards)
            new_state.enemy_health -= damage
            new_state.enemy_attack_counter -= 1
        elif suggested_action.type == "discard":
            if new_state.discard_count > 0:
                new_state.discard_count -= 1
                self.log("Applied discard action.")
            else:
                messagebox.showerror("Error", "No discards available!")
                return

        new_state.end_turn()

        self.player_health_var.set(str(new_state.player_health))
        self.enemy_health_var.set(str(int(new_state.enemy_health)))
        self.enemy_attack_counter_var.set(str(new_state.enemy_attack_counter))
        self.discard_count_var.set(str(new_state.discard_count))
        self.enemy_base_counter_var.set(str(new_state.enemy_base_counter))

        self.game_state = new_state
        prev_hand = new_state.hand

        self.log("Action applied. Game state values updated based on simulation.")
        suggested_action = None
        self.suggestion_text.config(state="normal")
        self.suggestion_text.delete("1.0", tk.END)
        self.suggestion_text.config(state="disabled")
        self.reset_progress()

    def reset_game(self):
        """
        Resets the deck, clears the hand UI, and restores default values.
        """
        global persistent_deck, suggested_action
        persistent_deck = Deck()
        suggested_action = None
        self.suggestion_text.config(state="normal")
        self.suggestion_text.delete("1.0", tk.END)

        for widget in self.hand_frame.winfo_children():
            grid_row = widget.grid_info().get("row", 0)
            if grid_row not in (0, 1, 100):
                widget.destroy()
        self.card_rows.clear()
        self.current_hand = []

        self.player_health_var.set("100")
        self.enemy_health_var.set("200")
        self.enemy_attack_power_var.set("3")
        self.enemy_attack_counter_var.set("2")
        self.discard_count_var.set("3")
        self.enemy_base_counter_var.set("3")
        self.deck_size_var.set(len(persistent_deck.cards))

        self.log("Game has been reset.")

    # --------------------------------------------------------------------------
    # Deck Editor (manual deck editing)
    # --------------------------------------------------------------------------
    def open_deck_editor(self):
        """Opens a window with a 4x13 grid of checkboxes to manually edit the deck."""
        global persistent_deck
        editor = tk.Toplevel(self)
        editor.title("Edit Deck")
        editor.grab_set()  # modal

        checkbox_vars = {}
        hand_numbers = {card.number for card in self.current_hand}

        for i, suit in enumerate(SUITS):
            ttk.Label(editor, text=suit, font=("TkDefaultFont", 10, "bold")).grid(row=i+1, column=0, padx=3, pady=3)
        for j, rank in enumerate(RANKS):
            ttk.Label(editor, text=rank, font=("TkDefaultFont", 10, "bold")).grid(row=0, column=j+1, padx=3, pady=3)
        if persistent_deck is not None:
            persistent_deck.external_draw(self.current_hand)
            self.deck_size_var.set(str(len(persistent_deck.cards)))
        for i, suit in enumerate(SUITS):
            for j, rank in enumerate(RANKS):
                card_obj = Card(suit, rank)
                var = tk.IntVar()
                if persistent_deck is not None and card_obj.number in persistent_deck.cards:
                    var.set(1)
                else:
                    var.set(0)
                checkbox_vars[(suit, rank)] = var
                cb = tk.Checkbutton(editor, variable=var)
                if card_obj.number in hand_numbers:
                    cb.config(state="disabled")
                cb.grid(row=i+1, column=j+1, padx=2, pady=2)

        def save_deck():
            global persistent_deck
            new_cards = []
            for (suit, rank), var in checkbox_vars.items():
                if var.get() == 1:
                    temp_card = Card(suit, rank)
                    new_cards.append(temp_card.number)
            if persistent_deck is None:
                persistent_deck = Deck(new_cards)
            else:
                persistent_deck.cards = new_cards
            self.deck_size_var.set(str(len(persistent_deck.cards)))
            self.log("Deck has been updated via manual editing.")
            editor.destroy()

        save_button = ttk.Button(editor, text="Save", command=save_deck)
        save_button.grid(row=len(SUITS)+1, column=0, columnspan=len(RANKS)//2, padx=5, pady=5, sticky="ew")
        cancel_button = ttk.Button(editor, text="Cancel", command=editor.destroy)
        cancel_button.grid(row=len(SUITS)+1, column=(len(RANKS)//2)+1, columnspan=len(RANKS)//2, padx=5, pady=5, sticky="ew")

if __name__ == "__main__":
    app = GameApp()
    app.mainloop()
