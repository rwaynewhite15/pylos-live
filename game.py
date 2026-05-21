"""
Pylos - Game logic.

Board:  4 levels of (size 4,3,2,1) -> 30 slots total.
Each player starts with 15 marbles.

Turn flow:
  1) Player makes ONE of:
       - PLACE a marble from reserve onto an empty, fully-supported slot
       - LIFT one of their marbles to a higher level (slot must be empty
         and fully-supported once the source is removed; lifted marble must
         not be supporting anything above it).
  2) If the move triggered a bonus (placed on level >= 2, OR a 2x2
     square of the player's OWN marbles was just formed), the player MAY
     retrieve 1 or 2 of their own non-supporting marbles back to reserve.
  3) Otherwise pass the turn.

WIN: place/lift the apex marble (level 4).
LOSS: the player whose turn it is has no legal placement and no legal lift.
"""

INITIAL_MARBLES = 15
NUM_LEVELS = 4
AI_STARTUP_DELAY = 0.8
AI_MOVE_DELAY = 0.4


def level_size(level):
    return NUM_LEVELS - level


def all_coords():
    out = []
    for lv in range(NUM_LEVELS):
        s = level_size(lv)
        for r in range(s):
            for c in range(s):
                out.append((lv, r, c))
    return out


class PylosGame:
    def __init__(self, first_player=0):
        # board[level][row][col] -> None or player id (0 or 1)
        self.board = [
            [[None] * level_size(lv) for _ in range(level_size(lv))]
            for lv in range(NUM_LEVELS)
        ]
        self.reserve = {0: INITIAL_MARBLES, 1: INITIAL_MARBLES}
        self.current_player = first_player
        self.game_over = False
        self.winner = None
        # When non-None, the current player has triggered a bonus and may
        # retrieve up to (2 - len(self.retrievals_taken)) marbles.
        self.retrieve_open = False
        self.retrievals_taken = []
        self.last_move = None  # dict describing the last action

    # ── Geometry helpers ────────────────────────────────────────────────

    def get(self, lv, r, c):
        return self.board[lv][r][c]

    def in_bounds(self, lv, r, c):
        if not (0 <= lv < NUM_LEVELS):
            return False
        s = level_size(lv)
        return 0 <= r < s and 0 <= c < s

    def is_supported(self, lv, r, c):
        """Slot has all 4 supporting marbles below it (or is on level 0)."""
        if lv == 0:
            return True
        b = self.board[lv - 1]
        return (b[r][c] is not None and b[r + 1][c] is not None
                and b[r][c + 1] is not None and b[r + 1][c + 1] is not None)

    def is_supporting(self, lv, r, c):
        """A marble at this slot supports at least one marble above."""
        if lv >= NUM_LEVELS - 1:
            return False
        above = self.board[lv + 1]
        s = level_size(lv + 1)
        for r2 in range(max(0, r - 1), min(s, r + 1)):
            for c2 in range(max(0, c - 1), min(s, c + 1)):
                if above[r2][c2] is not None:
                    return True
        return False

    def available_placements(self, lv):
        s = level_size(lv)
        out = []
        for r in range(s):
            for c in range(s):
                if self.board[lv][r][c] is None and self.is_supported(lv, r, c):
                    out.append((lv, r, c))
        return out

    def liftable_marbles(self, player):
        out = []
        for lv in range(NUM_LEVELS):
            s = level_size(lv)
            for r in range(s):
                for c in range(s):
                    if (self.board[lv][r][c] == player
                            and not self.is_supporting(lv, r, c)):
                        out.append((lv, r, c))
        return out

    def completes_own_square(self, lv, r, c, player):
        """True if placing/lifting at (lv,r,c) for `player` just created a
        2x2 supporting square of that player's marbles directly under an
        upper slot."""
        if lv >= NUM_LEVELS - 1:
            return False
        b = self.board[lv]
        s = level_size(lv + 1)
        for r2 in range(max(0, r - 1), min(s, r + 1)):
            for c2 in range(max(0, c - 1), min(s, c + 1)):
                # The 2x2 below (lv+1,r2,c2) is (lv,r2,c2),(lv,r2+1,c2),
                # (lv,r2,c2+1),(lv,r2+1,c2+1). Check all are this player.
                cells = [b[r2][c2], b[r2 + 1][c2],
                         b[r2][c2 + 1], b[r2 + 1][c2 + 1]]
                if all(x == player for x in cells):
                    return True
        return False

    # ── Move helpers ────────────────────────────────────────────────────

    def valid_moves(self, player=None):
        """Return list of move dicts (lift+place only). Used for AI search."""
        if player is None:
            player = self.current_player
        moves = []
        if self.reserve[player] > 0:
            for lv in range(NUM_LEVELS):
                for (l, r, c) in self.available_placements(lv):
                    moves.append({"type": "place", "to": (l, r, c)})
        # Lift moves
        liftable = self.liftable_marbles(player)
        for (fl, fr, fc) in liftable:
            for tl in range(fl + 1, NUM_LEVELS):
                for (_, tr, tc) in self.available_placements(tl):
                    # Once we remove the source, check support still holds.
                    self.board[fl][fr][fc] = None
                    ok = self.is_supported(tl, tr, tc)
                    self.board[fl][fr][fc] = player
                    if ok:
                        moves.append({"type": "lift", "from": (fl, fr, fc), "to": (tl, tr, tc)})
        return moves

    def has_any_move(self, player):
        if self.reserve[player] > 0:
            for lv in range(NUM_LEVELS):
                if self.available_placements(lv):
                    return True
        # Quick lift check
        for (fl, fr, fc) in self.liftable_marbles(player):
            for tl in range(fl + 1, NUM_LEVELS):
                for (_, tr, tc) in self.available_placements(tl):
                    self.board[fl][fr][fc] = None
                    ok = self.is_supported(tl, tr, tc)
                    self.board[fl][fr][fc] = player
                    if ok:
                        return True
        return False

    # ── Public actions ──────────────────────────────────────────────────

    def make_place(self, player, lv, r, c):
        if self.game_over:
            return False, "Game already over"
        if self.retrieve_open:
            return False, "Resolve retrieval first"
        if player != self.current_player:
            return False, "Not your turn"
        if not self.in_bounds(lv, r, c):
            return False, "Position out of bounds"
        if self.reserve[player] <= 0:
            return False, "No marbles in reserve"
        if self.board[lv][r][c] is not None:
            return False, "Position occupied"
        if not self.is_supported(lv, r, c):
            return False, "Position not supported"

        self.board[lv][r][c] = player
        self.reserve[player] -= 1

        self.last_move = {"player": player, "type": "place", "to": (lv, r, c)}

        # Apex win
        if lv == NUM_LEVELS - 1:
            self._finish(player)
            return True, "OK"

        bonus = (lv >= 1) or self.completes_own_square(lv, r, c, player)
        if bonus and self.liftable_marbles(player):
            self.retrieve_open = True
            self.retrievals_taken = []
        else:
            self._end_turn()
        return True, "OK"

    def make_lift(self, player, fl, fr, fc, tl, tr, tc):
        if self.game_over:
            return False, "Game already over"
        if self.retrieve_open:
            return False, "Resolve retrieval first"
        if player != self.current_player:
            return False, "Not your turn"
        if not self.in_bounds(fl, fr, fc) or not self.in_bounds(tl, tr, tc):
            return False, "Position out of bounds"
        if tl <= fl:
            return False, "Target must be higher level"
        if self.board[fl][fr][fc] != player:
            return False, "Not your marble"
        if self.is_supporting(fl, fr, fc):
            return False, "Marble is supporting another"
        if self.board[tl][tr][tc] is not None:
            return False, "Target occupied"

        # Tentatively remove source to check support at target.
        self.board[fl][fr][fc] = None
        if not self.is_supported(tl, tr, tc):
            self.board[fl][fr][fc] = player
            return False, "Target not supported"
        self.board[tl][tr][tc] = player

        self.last_move = {"player": player, "type": "lift",
                          "from": (fl, fr, fc), "to": (tl, tr, tc)}

        if tl == NUM_LEVELS - 1:
            self._finish(player)
            return True, "OK"

        # Lifting always grants the bonus (always goes higher).
        bonus = True
        # Also a square may have been formed at the from-level neighborhood
        # by lifting -- no, lifting removes a marble, can't form a square.
        # But moving up may form a square at the target level:
        bonus = bonus or self.completes_own_square(tl, tr, tc, player)

        if bonus and self.liftable_marbles(player):
            self.retrieve_open = True
            self.retrievals_taken = []
        else:
            self._end_turn()
        return True, "OK"

    def make_retrieve(self, player, lv, r, c):
        """Retrieve a single marble. Call up to twice while retrieve_open."""
        if not self.retrieve_open:
            return False, "Not retrieving"
        if player != self.current_player:
            return False, "Not your turn"
        if not self.in_bounds(lv, r, c):
            return False, "Position out of bounds"
        if self.board[lv][r][c] != player:
            return False, "Not your marble"
        if self.is_supporting(lv, r, c):
            return False, "Marble is supporting another"
        if len(self.retrievals_taken) >= 2:
            return False, "Already retrieved 2"

        self.board[lv][r][c] = None
        self.reserve[player] += 1
        self.retrievals_taken.append((lv, r, c))

        # Auto-close if no more liftable own marbles or 2 already taken.
        if len(self.retrievals_taken) >= 2 or not self.liftable_marbles(player):
            self._end_turn()
        return True, "OK"

    def skip_retrieve(self, player):
        if not self.retrieve_open:
            return False, "Not retrieving"
        if player != self.current_player:
            return False, "Not your turn"
        self._end_turn()
        return True, "OK"

    # ── Turn flow ───────────────────────────────────────────────────────

    def _end_turn(self):
        self.retrieve_open = False
        self.retrievals_taken = []
        nxt = 1 - self.current_player
        self.current_player = nxt
        # If opponent has no legal move, current player wins.
        if not self.has_any_move(nxt):
            self._finish(1 - nxt)

    def _finish(self, winner):
        self.game_over = True
        self.winner = winner

    # ── Serialization ───────────────────────────────────────────────────

    def state(self):
        return {
            "board": self.board,
            "reserve": self.reserve,
            "current_player": self.current_player,
            "game_over": self.game_over,
            "winner": self.winner,
            "retrieve_open": self.retrieve_open,
            "retrievals_taken": self.retrievals_taken,
            "last_move": self.last_move,
        }

    def copy(self):
        g = PylosGame.__new__(PylosGame)
        g.board = [[row[:] for row in lvl] for lvl in self.board]
        g.reserve = dict(self.reserve)
        g.current_player = self.current_player
        g.game_over = self.game_over
        g.winner = self.winner
        g.retrieve_open = self.retrieve_open
        g.retrievals_taken = list(self.retrievals_taken)
        g.last_move = None
        return g
