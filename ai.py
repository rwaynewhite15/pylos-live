"""
Pylos - AI logic.

Heuristic + alpha-beta minimax search over a compact action model that
collapses (place|lift) and (optional retrievals) into a single super-move
per turn.
"""
import random

from game import NUM_LEVELS, level_size


def _heuristic(game, ai_player):
    opp = 1 - ai_player
    score = 0

    # Reserve advantage — each saved marble is worth more now that we look deeper.
    score += (game.reserve[ai_player] - game.reserve[opp]) * 1.5

    # Positional value — exponentially more valuable at higher levels.
    for lv in range(NUM_LEVELS):
        s = level_size(lv)
        weight = 1.0 + lv * 2.0
        for r in range(s):
            for c in range(s):
                v = game.board[lv][r][c]
                if v is None:
                    continue
                if v == ai_player:
                    score += weight
                else:
                    score -= weight

    # Formation analysis: 2×2 squares that support placement on the level above.
    # Complete formations and near-complete unblocked ones are heavily rewarded.
    for lv in range(NUM_LEVELS - 1):
        s = level_size(lv)
        fw = 2.0 * (lv + 1)   # scales with level: 2, 4, 6
        for r in range(s - 1):
            for c in range(s - 1):
                cells = [game.board[lv][r + dr][c + dc]
                         for dr in range(2) for dc in range(2)]
                ai_cnt = sum(1 for v in cells if v == ai_player)
                opp_cnt = sum(1 for v in cells if v == opp)
                if ai_cnt == 4:
                    score += fw * 2.0
                elif opp_cnt == 4:
                    score -= fw * 2.0
                elif ai_cnt == 3 and opp_cnt == 0:
                    score += fw
                elif opp_cnt == 3 and ai_cnt == 0:
                    score -= fw

    return score


def _enumerate_super_moves(game):
    """Return list of (action_sequence, resulting_game) for current player.

    Retrieval branching is pruned: when a bonus opens, the AI considers
    (a) take the two lowest-level non-supporting marbles, and (b) skip.
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
            # Option A: skip
            g_skip = g2.copy()
            g_skip.skip_retrieve(player)
            result.append(([mv, {"type": "skip"}], g_skip))
            # Option B: take two lowest-level non-supporting (or just one if only one)
            if liftable:
                pos = liftable[0]
                g1 = g2.copy()
                ok, _ = g1.make_retrieve(player, *pos)
                if ok and g1.retrieve_open:
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
                            continue
                    g1b = g1.copy()
                    g1b.skip_retrieve(player)
                    result.append(([mv, {"type": "retrieve", "at": pos},
                                   {"type": "skip"}], g1b))
                elif ok:
                    result.append(([mv, {"type": "retrieve", "at": pos}], g1))
        else:
            result.append(([mv], g2))
    return result


# Max moves considered at each internal minimax node.
# Ordering ensures we keep the best-looking moves, so pruning is aggressive.
_INTERNAL_CAP = 25


def _minimax(game, depth, alpha, beta, ai_player):
    if game.game_over:
        if game.winner == ai_player:
            return 1000.0
        if game.winner is None:
            return 0.0
        return -1000.0
    if depth == 0:
        return _heuristic(game, ai_player)

    supers = _enumerate_super_moves(game)
    if not supers:
        return _heuristic(game, ai_player)

    maximizing = (game.current_player == ai_player)
    # Sort so the most promising moves come first — this is what makes alpha-beta
    # prune aggressively instead of wandering through bad branches.
    supers.sort(key=lambda tup: _heuristic(tup[1], ai_player), reverse=maximizing)
    if len(supers) > _INTERNAL_CAP:
        supers = supers[:_INTERNAL_CAP]

    best = float("-inf") if maximizing else float("inf")
    for _seq, g2 in supers:
        val = _minimax(g2, depth - 1, alpha, beta, ai_player)
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
    """Sort by heuristic score (best for ai_player first) and keep top `cap`."""
    supers.sort(key=lambda tup: _heuristic(tup[1], ai_player), reverse=True)
    return supers[:cap]


def get_ai_super_move(game, difficulty):
    """Return list of actions for the AI to play out (place/lift + retrieves)."""
    supers = _enumerate_super_moves(game)
    if not supers:
        return None

    if difficulty == "easy":
        seq, _ = random.choice(supers)
        return seq

    ai_player = game.current_player
    depth = 2 if difficulty == "medium" else 4
    cap = 60 if difficulty == "medium" else 120
    supers = _order_supers(supers, ai_player, cap)

    best_score = float("-inf")
    best_seq = supers[0][0]
    for seq, g2 in supers:
        s = _minimax(g2, depth - 1, float("-inf"), float("inf"), ai_player)
        if s > best_score:
            best_score = s
            best_seq = seq
    return best_seq
