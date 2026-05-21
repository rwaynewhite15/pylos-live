"""
Pylos - AI logic.

Hard difficulty uses iterative deepening alpha-beta with a time budget.
Each iteration's best move is used to order the next iteration, so deeper
plies prune aggressively. A position-aware heuristic punishes own marbles
that are stuck supporting opponent stones, rewards completed and near-
complete formations, and weights higher levels exponentially.
"""
import random
import time

from game import NUM_LEVELS, level_size


# Positional value per level (exponential — apex matters most).
_POS_WEIGHT = [1.0, 3.5, 9.0, 20.0]

# Internal node cap for the search (keeps width manageable at depth).
_INTERNAL_CAP = 30


def _heuristic(game, ai_player):
    """Evaluate a non-terminal position from ai_player's POV. Higher is better."""
    opp = 1 - ai_player
    board = game.board
    score = 0.0

    # ── Apex threat: huge weight, dominates other terms. ────────────────────
    # If level 2 (the 2x2 supporting apex) is fully filled and the next
    # player has any way to place or lift onto the apex, the game is
    # effectively decided. Detect that here so the search sees it at the
    # leaves without needing extra plies.
    if board[3][0][0] is None:
        lvl2 = board[2]
        lvl2_full = (lvl2[0][0] is not None and lvl2[0][1] is not None
                     and lvl2[1][0] is not None and lvl2[1][1] is not None)
        if lvl2_full:
            nxt = game.current_player
            # Can `nxt` reach the apex on their next move?
            #   Direct placement: needs reserve.
            #   Lift: any own marble on lvl 0/1 that is not supporting anything.
            #         (Level 2 marbles are all supporting the apex slot itself.)
            can_apex = game.reserve[nxt] > 0
            if not can_apex:
                for (lv, r, c) in game.liftable_marbles(nxt):
                    if lv < 2:
                        can_apex = True
                        break
            if can_apex:
                score += 500.0 if nxt == ai_player else -500.0

    # ── Reserve advantage. Each saved marble = future placement. ────────────
    score += (game.reserve[ai_player] - game.reserve[opp]) * 3.0

    # ── Per-marble positional value, devalued if "wasted" (supports opp). ──
    for lv in range(NUM_LEVELS):
        s = level_size(lv)
        for r in range(s):
            for c in range(s):
                v = board[lv][r][c]
                if v is None:
                    continue
                w = _POS_WEIGHT[lv]
                if lv < NUM_LEVELS - 1:
                    above_s = level_size(lv + 1)
                    supports_opp = False
                    for r2 in range(max(0, r - 1), min(above_s, r + 1)):
                        for c2 in range(max(0, c - 1), min(above_s, c + 1)):
                            x = board[lv + 1][r2][c2]
                            if x is not None and x != v:
                                supports_opp = True
                                break
                        if supports_opp:
                            break
                    if supports_opp:
                        w *= 0.30
                if v == ai_player:
                    score += w
                else:
                    score -= w

    # ── 2x2 formation pressure. Threats now scaled higher — the reserve
    # race is the whole game and a 3-unblocked square is a free +2 marbles
    # next move. Weight rises with level since higher squares matter more.
    for lv in range(NUM_LEVELS - 1):
        s = level_size(lv)
        threat_w = 3.0 + lv * 3.5
        for r in range(s - 1):
            for c in range(s - 1):
                cells = (board[lv][r][c], board[lv][r + 1][c],
                         board[lv][r][c + 1], board[lv][r + 1][c + 1])
                ai_cnt = cells.count(ai_player)
                opp_cnt = cells.count(opp)
                if ai_cnt == 4:
                    score += threat_w * 3.0
                elif opp_cnt == 4:
                    score -= threat_w * 3.0
                elif ai_cnt == 3 and opp_cnt == 0:
                    score += threat_w * 2.0
                elif opp_cnt == 3 and ai_cnt == 0:
                    score -= threat_w * 2.0
                elif ai_cnt == 2 and opp_cnt == 0:
                    score += threat_w * 0.6
                elif opp_cnt == 2 and ai_cnt == 0:
                    score -= threat_w * 0.6

    # ── Mobility — non-pinned own marbles give lift flexibility. ────────────
    ai_lifts = len(game.liftable_marbles(ai_player))
    opp_lifts = len(game.liftable_marbles(opp))
    score += (ai_lifts - opp_lifts) * 0.5

    return score


def _enumerate_super_moves(game):
    """Return list of (action_sequence, resulting_game) for current player.

    Retrieval branching: when a bonus opens we consider skip, take-1, take-2
    (lowest-level non-supporting marbles). Limited width keeps search fast.
    """
    base_moves = game.valid_moves()
    result = []
    for mv in base_moves:
        g2 = game.copy()
        player = g2.current_player
        if mv["type"] == "place":
            lv, r, c = mv["to"]
            g2.make_place(player, lv, r, c)
        else:
            fl, fr, fc = mv["from"]
            tl, tr, tc = mv["to"]
            g2.make_lift(player, fl, fr, fc, tl, tr, tc)

        if g2.retrieve_open:
            liftable = sorted(g2.liftable_marbles(player), key=lambda x: x[0])
            # (A) skip the bonus entirely
            g_skip = g2.copy()
            g_skip.skip_retrieve(player)
            result.append(([mv, {"type": "skip"}], g_skip))
            if not liftable:
                continue
            pos = liftable[0]
            g1 = g2.copy()
            ok, _ = g1.make_retrieve(player, *pos)
            if not ok:
                continue
            # (B) take 1 (lowest), then stop
            if g1.retrieve_open:
                g1_stop = g1.copy()
                g1_stop.skip_retrieve(player)
                result.append(([mv, {"type": "retrieve", "at": pos},
                               {"type": "skip"}], g1_stop))
                # (C) take 2 (lowest two)
                liftable2 = sorted(g1.liftable_marbles(player), key=lambda x: x[0])
                if liftable2:
                    pos2 = liftable2[0]
                    g2b = g1.copy()
                    ok2, _ = g2b.make_retrieve(player, *pos2)
                    if ok2:
                        result.append(([mv,
                                        {"type": "retrieve", "at": pos},
                                        {"type": "retrieve", "at": pos2}],
                                       g2b))
            else:
                # retrieval auto-closed (1 was the only available)
                result.append(([mv, {"type": "retrieve", "at": pos}], g1))
        else:
            result.append(([mv], g2))
    return result


class _Timeout(Exception):
    pass


def _minimax(game, depth, alpha, beta, ai_player, deadline):
    if deadline is not None and time.monotonic() > deadline:
        raise _Timeout
    if game.game_over:
        if game.winner == ai_player:
            return 10000.0
        if game.winner is None:
            return 0.0
        return -10000.0
    if depth == 0:
        return _heuristic(game, ai_player)

    supers = _enumerate_super_moves(game)
    if not supers:
        return _heuristic(game, ai_player)

    maximizing = (game.current_player == ai_player)
    # Order children by static eval so cutoffs trigger early.
    supers.sort(key=lambda tup: _heuristic(tup[1], ai_player), reverse=maximizing)
    if len(supers) > _INTERNAL_CAP:
        supers = supers[:_INTERNAL_CAP]

    best = float("-inf") if maximizing else float("inf")
    for _seq, g2 in supers:
        val = _minimax(g2, depth - 1, alpha, beta, ai_player, deadline)
        if maximizing:
            if val > best:
                best = val
            if best > alpha:
                alpha = best
        else:
            if val < best:
                best = val
            if best < beta:
                beta = best
        if beta <= alpha:
            break
    return best


def _order_supers(supers, ai_player, cap):
    supers.sort(key=lambda tup: _heuristic(tup[1], ai_player), reverse=True)
    return supers[:cap]


def _iterative_deepening(root_supers, ai_player, max_depth, time_limit):
    """Search root_supers with iterative deepening. Returns (best_seq, depth_reached)."""
    start = time.monotonic()
    deadline = start + time_limit
    # Start with static-eval order; refine after each completed depth.
    ordering = list(range(len(root_supers)))
    best_seq = root_supers[ordering[0]][0]
    depth_done = 0

    for d in range(1, max_depth + 1):
        # If we've already used 60% of the budget, don't start a new (more
        # expensive) depth — we'd likely time out mid-iteration.
        elapsed = time.monotonic() - start
        if d > 1 and elapsed > time_limit * 0.6:
            break

        try:
            iter_scores = []
            iter_best_score = float("-inf")
            iter_best_seq = root_supers[ordering[0]][0]
            alpha = float("-inf")
            for idx in ordering:
                seq, g2 = root_supers[idx]
                # After our move it's opponent's turn — minimizing side.
                score = _minimax(g2, d - 1, alpha, float("inf"),
                                 ai_player, deadline)
                iter_scores.append((idx, score))
                if score > iter_best_score:
                    iter_best_score = score
                    iter_best_seq = seq
                    if score > alpha:
                        alpha = score
            # Commit this iteration's result.
            best_seq = iter_best_seq
            depth_done = d
            # Re-order: best move first next iteration → biggest pruning win.
            iter_scores.sort(key=lambda x: x[1], reverse=True)
            ordering = [idx for idx, _ in iter_scores]
        except _Timeout:
            break

    return best_seq, depth_done


def get_ai_super_move(game, difficulty):
    """Return list of actions for the AI to play out (place/lift + retrieves)."""
    supers = _enumerate_super_moves(game)
    if not supers:
        return None

    if difficulty == "easy":
        seq, _ = random.choice(supers)
        return seq

    ai_player = game.current_player

    if difficulty == "medium":
        max_depth = 3
        cap = 60
        time_limit = 0.8
    else:  # hard
        max_depth = 8        # iterative deepening will rarely reach this
        cap = 180
        time_limit = 4.0

    supers = _order_supers(supers, ai_player, cap)
    if len(supers) == 1:
        return supers[0][0]

    best_seq, _ = _iterative_deepening(supers, ai_player, max_depth, time_limit)
    return best_seq
