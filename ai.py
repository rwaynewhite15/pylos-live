"""
Pylos - AI logic.

Heuristic + alpha-beta minimax search over a compact action model that
collapses (place|lift) and (optional retrievals) into a single super-move
per turn. The branching factor is large near the start but shrinks fast.
"""
import random
import itertools

from game import NUM_LEVELS, level_size


def _heuristic(game, ai_player):
    opp = 1 - ai_player
    score = 0
    # Reserve advantage (each saved marble is worth ~1 unit).
    score += (game.reserve[ai_player] - game.reserve[opp]) * 1.0
    # Marbles on higher levels are valuable.
    for lv in range(NUM_LEVELS):
        s = level_size(lv)
        for r in range(s):
            for c in range(s):
                v = game.board[lv][r][c]
                if v is None:
                    continue
                weight = 0.4 + lv * 0.7
                if v == ai_player:
                    score += weight
                else:
                    score -= weight
    return score


def _enumerate_super_moves(game):
    """Return list of (action_sequence, resulting_game) for current player.

    Retrieval branching is pruned aggressively: when a bonus opens, the AI
    only considers (a) take the two lowest-level non-supporting marbles, and
    (b) skip. This keeps the branching factor manageable at depth 2-3.
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
            # Option B: take two lowest-level non-supporting (or just one if only one available)
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


def _limit_supers(supers, cap):
    """Trim a super-move list to a manageable size by sampling."""
    if len(supers) <= cap:
        return supers
    random.shuffle(supers)
    return supers[:cap]


def get_ai_super_move(game, difficulty):
    """Return list of actions for the AI to play out (place/lift + retrieves)."""
    supers = _enumerate_super_moves(game)
    if not supers:
        return None

    if difficulty == "easy":
        seq, _ = random.choice(supers)
        return seq

    depth = 2 if difficulty == "medium" else 3
    cap = 60 if difficulty == "medium" else 120
    supers = _limit_supers(supers, cap)

    ai_player = game.current_player
    best_score = float("-inf")
    best_seq = supers[0][0]
    for seq, g2 in supers:
        s = _minimax(g2, depth - 1, float("-inf"), float("inf"), ai_player)
        if s > best_score:
            best_score = s
            best_seq = seq
    return best_seq
