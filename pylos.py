"""
Pylos - Two-player marble pyramid game
---------------------------------------
Board: 4 levels  ->  4x4, 3x3, 2x2, 1x1  (30 slots total)
Each player starts with 15 marbles.

On your turn choose one action:
  P <level> <row> <col>   -- Place a marble from your reserve
  L <fl> <fr> <fc> <tl> <tr> <tc>  -- Lift one of your marbles to a higher level

A marble may be placed at level L only when the 4 marbles beneath it are filled.
Level 1 (bottom) is always accessible.

BONUS - retrieve 1 or 2 own marbles back to your reserve if:
  * You placed on level 2, 3, or 4  (higher than the base)
  * OR your placement completed a 2x2 square (making a new upper position available)
  Retrievable marbles must not be supporting anything above them.

WIN: place the apex marble (level 4, row 1, col 1).
LOSE: no marble to place and none to lift.
"""

# ── Board helpers ─────────────────────────────────────────────────────────────

def make_board():
    return [[[None] * (4 - lv) for _ in range(4 - lv)] for lv in range(4)]


def size(level):
    return 4 - level


def is_supported(board, level, row, col):
    """True if position (level,row,col) has all 4 supports below it."""
    if level == 0:
        return True
    b = board[level - 1]
    return (b[row][col] is not None and b[row + 1][col] is not None and
            b[row][col + 1] is not None and b[row + 1][col + 1] is not None)


def is_supporting(board, level, row, col):
    """True if the marble at (level,row,col) has any marble resting on it."""
    if level >= 3:
        return False
    above = board[level + 1]
    s = size(level + 1)
    for r2 in range(max(0, row - 1), min(s, row + 1)):
        for c2 in range(max(0, col - 1), min(s, col + 1)):
            if above[r2][c2] is not None:
                return True
    return False


def available_placements(board, level):
    """Empty, fully-supported positions at this level."""
    s = size(level)
    return [(r, c) for r in range(s) for c in range(s)
            if board[level][r][c] is None and is_supported(board, level, r, c)]


def liftable_marbles(board, player):
    """Positions of player's marbles that are not supporting anything above."""
    result = []
    for lv in range(4):
        s = size(lv)
        for r in range(s):
            for c in range(s):
                if board[lv][r][c] == player and not is_supporting(board, lv, r, c):
                    result.append((lv, r, c))
    return result


def completes_square(board, level, row, col):
    """True if placing at (level,row,col) just completed a supporting square."""
    if level >= 3:
        return False
    s = size(level + 1)
    for r2 in range(max(0, row - 1), min(s, row + 1)):
        for c2 in range(max(0, col - 1), min(s, col + 1)):
            if is_supported(board, level + 1, r2, c2):
                return True
    return False


# ── Display ───────────────────────────────────────────────────────────────────

SYMBOL = {None: ".", 1: "O", 2: "X"}


def print_board(board):
    print()
    for lv in range(3, -1, -1):
        s = size(lv)
        indent = "    " * (3 - lv)
        label = f"Level {lv + 1} ({s}x{s}):"
        print(f"  {label}")
        for r in range(s):
            row_str = "  ".join(SYMBOL[board[lv][r][c]] for c in range(s))
            col_nums = "  ".join(str(c + 1) for c in range(s))
            print(f"  {indent}r{r + 1}: {row_str}")
        # column header
        print(f"  {indent}    {col_nums}")
        print()


# ── Input parsing ─────────────────────────────────────────────────────────────

def parse_place(tokens):
    """Parse 'P level row col' -> (level-1, row-1, col-1) or None."""
    if len(tokens) != 4 or tokens[0].upper() != "P":
        return None
    try:
        return (int(tokens[1]) - 1, int(tokens[2]) - 1, int(tokens[3]) - 1)
    except ValueError:
        return None


def parse_lift(tokens):
    """Parse 'L fl fr fc tl tr tc' -> ((fl,fr,fc),(tl,tr,tc)) or None."""
    if len(tokens) != 7 or tokens[0].upper() != "L":
        return None
    try:
        coords = [int(x) - 1 for x in tokens[1:]]
        return (coords[0], coords[1], coords[2]), (coords[3], coords[4], coords[5])
    except ValueError:
        return None


# ── Retrieval phase ───────────────────────────────────────────────────────────

def retrieval_phase(board, reserve, player):
    """Offer player the chance to take back 1 or 2 marbles."""
    candidates = liftable_marbles(board, player)
    if not candidates:
        return

    print("  >> BONUS: you may retrieve 1 or 2 of your marbles (or press Enter to skip).")
    print("     Retrievable:")
    for lv, r, c in candidates:
        print(f"       Level {lv + 1}  r{r + 1}  c{c + 1}")
    print("     Enter up to 2 positions as: <level> <row> <col>  [level row col]")

    taken = 0
    while taken < 2:
        raw = input("  retrieve> ").strip()
        if not raw:
            break
        parts = raw.split()
        # allow two positions on one line
        positions = []
        i = 0
        while i + 2 < len(parts):
            try:
                positions.append((int(parts[i]) - 1, int(parts[i + 1]) - 1, int(parts[i + 2]) - 1))
            except ValueError:
                print("  Bad input, skipped.")
            i += 3

        for lv, r, c in positions:
            if taken >= 2:
                break
            if (lv, r, c) not in candidates:
                print(f"  Can't retrieve Level {lv+1} r{r+1} c{c+1} (not eligible).")
                continue
            board[lv][r][c] = None
            reserve[player] += 1
            taken += 1
            candidates = liftable_marbles(board, player)  # refresh
            print(f"  Retrieved Level {lv+1} r{r+1} c{c+1}. Reserve now {reserve[player]}.")

        if taken >= 2 or not raw:
            break


# ── Main game loop ────────────────────────────────────────────────────────────

def play():
    board = make_board()
    reserve = {1: 15, 2: 15}
    current = 1

    print(__doc__)
    print("Player 1 = O   Player 2 = X")
    print("Positions are 1-based.  Example:  P 1 3 2  means level 1, row 3, col 2")
    input("Press Enter to start...")

    while True:
        print_board(board)
        opponent = 3 - current
        print(f"  Player {current} ({SYMBOL[current]}) | Reserve: P1={reserve[1]}  P2={reserve[2]}")

        # Check if the current player has any legal move
        can_place = reserve[current] > 0 and any(
            available_placements(board, lv) for lv in range(4)
        )
        can_lift_any = bool(liftable_marbles(board, current))

        if not can_place and not can_lift_any:
            print(f"\n  Player {current} has no moves!  Player {opponent} WINS!")
            return

        print(f"  Commands:  P <level> <row> <col>  |  L <from_level> <fr> <fc> <to_level> <tr> <tc>")
        raw = input("  > ").strip()
        tokens = raw.split()

        placed_level = None
        bonus = False

        # ── PLACE ──────────────────────────────────────────────────────────────
        coords = parse_place(tokens)
        if coords is not None:
            lv, r, c = coords
            if not (0 <= lv <= 3):
                print("  Invalid level (1-4)."); continue
            s = size(lv)
            if not (0 <= r < s and 0 <= c < s):
                print(f"  Invalid position for level {lv+1} (max row/col = {s})."); continue
            if reserve[current] == 0:
                print("  No marbles in reserve."); continue
            if board[lv][r][c] is not None:
                print("  Position already occupied."); continue
            if not is_supported(board, lv, r, c):
                print("  Position not supported from below."); continue

            board[lv][r][c] = current
            reserve[current] -= 1
            placed_level = lv
            bonus = (lv > 0) or completes_square(board, lv, r, c)

        # ── LIFT ───────────────────────────────────────────────────────────────
        elif parse_lift(tokens) is not None:
            (fl, fr, fc), (tl, tr, tc) = parse_lift(tokens)
            valid = True

            if not (0 <= fl <= 3 and 0 <= tl <= 3):
                print("  Invalid level."); valid = False
            elif tl <= fl:
                print("  Target must be a higher level than source."); valid = False
            elif not (0 <= fr < size(fl) and 0 <= fc < size(fl)):
                print(f"  Source position out of range."); valid = False
            elif not (0 <= tr < size(tl) and 0 <= tc < size(tl)):
                print(f"  Target position out of range."); valid = False
            elif board[fl][fr][fc] != current:
                print("  That is not your marble."); valid = False
            elif is_supporting(board, fl, fr, fc):
                print("  Marble is supporting another — cannot lift."); valid = False
            elif board[tl][tr][tc] is not None:
                print("  Target position is occupied."); valid = False
            else:
                # temporarily remove to re-check support at target
                board[fl][fr][fc] = None
                if not is_supported(board, tl, tr, tc):
                    board[fl][fr][fc] = current
                    print("  Target position not supported."); valid = False

            if valid:
                board[tl][tr][tc] = current
                placed_level = tl
                bonus = True  # lifting always goes higher, so always grants bonus

        else:
            print("  Unrecognised command."); continue

        # ── Win check ──────────────────────────────────────────────────────────
        if placed_level == 3:
            print_board(board)
            print(f"  Player {current} ({SYMBOL[current]}) placed the APEX marble and WINS!")
            return

        # ── Bonus retrieval ────────────────────────────────────────────────────
        if placed_level is not None and bonus:
            retrieval_phase(board, reserve, current)

        current = opponent


if __name__ == "__main__":
    play()
