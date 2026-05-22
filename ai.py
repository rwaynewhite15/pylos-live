"""
Pylos - AI logic.

Hard difficulty uses iterative deepening alpha-beta with a time budget.
Each iteration's best move is used to order the next iteration, so deeper
plies prune aggressively. A position-aware heuristic punishes own marbles
that are stuck supporting opponent stones, rewards completed and near-
complete formations, and weights higher levels exponentially.

A transposition table memoizes (position) -> (depth, score, flag) so
positions reached via different move orders are not researched. When the
combined reserves drop low, the AI enters "endgame mode" and is given a
much larger time + depth budget — at that point the tree is small enough
that TT-augmented search approximates a strong solution.
"""
import random
import time

from game import NUM_LEVELS, level_size


# Transposition table flag values.
_TT_EXACT = 0
_TT_LOWER = 1
_TT_UPPER = 2


def _state_key(game):
    """Canonical hashable key for a Pylos position."""
    board = tuple(tuple(tuple(row) for row in lvl) for lvl in game.board)
    return (board, game.reserve[0], game.reserve[1],
            game.current_player, game.retrieve_open,
            tuple(sorted(game.retrievals_taken)))


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

    # Near-completion multipliers depend on whose turn it is. The side
    # about to move can complete (or block) immediately, so weights are
    # massively biased toward whoever moves next.
    next_is_ai = (game.current_player == ai_player)
    ai_near = 5.0 if next_is_ai else 2.0
    opp_near = 2.0 if next_is_ai else 5.0

    # ── 2x2 formation pressure. A 3-unblocked square is a free +2 marbles
    # for whoever closes it. Weight rises with level.
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
                    score += threat_w * ai_near
                elif opp_cnt == 3 and ai_cnt == 0:
                    score -= threat_w * opp_near
                elif ai_cnt == 2 and opp_cnt == 0:
                    score += threat_w * 0.8
                elif opp_cnt == 2 and ai_cnt == 0:
                    score -= threat_w * 0.8

    # ── Line (row/column) formation pressure. Same as squares — a 3-in-row
    # on lvl 1 or 4-in-row on lvl 0 also fires the bonus.
    for lv in (0, 1):
        s = level_size(lv)
        line_w = 4.0 + lv * 4.5
        for r in range(s):
            cells = tuple(board[lv][r][c] for c in range(s))
            ai_cnt = cells.count(ai_player)
            opp_cnt = cells.count(opp)
            if ai_cnt == s:
                score += line_w * 3.0
            elif opp_cnt == s:
                score -= line_w * 3.0
            elif ai_cnt == s - 1 and opp_cnt == 0:
                score += line_w * ai_near
            elif opp_cnt == s - 1 and ai_cnt == 0:
                score -= line_w * opp_near
            elif ai_cnt == s - 2 and opp_cnt == 0 and s >= 3:
                score += line_w * 0.6
            elif opp_cnt == s - 2 and ai_cnt == 0 and s >= 3:
                score -= line_w * 0.6
        for c in range(s):
            cells = tuple(board[lv][r][c] for r in range(s))
            ai_cnt = cells.count(ai_player)
            opp_cnt = cells.count(opp)
            if ai_cnt == s:
                score += line_w * 3.0
            elif opp_cnt == s:
                score -= line_w * 3.0
            elif ai_cnt == s - 1 and opp_cnt == 0:
                score += line_w * ai_near
            elif opp_cnt == s - 1 and ai_cnt == 0:
                score -= line_w * opp_near
            elif ai_cnt == s - 2 and opp_cnt == 0 and s >= 3:
                score += line_w * 0.6
            elif opp_cnt == s - 2 and ai_cnt == 0 and s >= 3:
                score -= line_w * 0.6

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


class _SearchCtx:
    """Bundles search-wide state: deadline, TT, ai_player, and progress
    reporting. Passed by reference through _minimax so we don't have to
    thread 7 positional args through every recursion."""
    __slots__ = ("ai_player", "deadline", "tt", "progress_cb",
                 "start", "time_limit", "nodes", "last_progress", "current_depth")

    def __init__(self, ai_player, time_limit, progress_cb=None):
        self.ai_player = ai_player
        self.start = time.monotonic()
        self.deadline = self.start + time_limit
        self.tt = {}
        self.progress_cb = progress_cb
        self.time_limit = time_limit
        self.nodes = 0
        self.last_progress = 0.0
        self.current_depth = 0

    def tick(self):
        self.nodes += 1
        # Throttled work: only check time and emit progress every 2048 nodes.
        if self.nodes & 2047 == 0:
            now = time.monotonic()
            if now > self.deadline:
                raise _Timeout
            if self.progress_cb is not None and now - self.last_progress > 0.1:
                self.last_progress = now
                try:
                    self.progress_cb(self.nodes, self.current_depth,
                                     now - self.start, self.time_limit)
                except Exception:
                    pass  # never let UI plumbing crash the search


def _minimax(game, depth, alpha, beta, ctx):
    ctx.tick()
    if game.game_over:
        if game.winner == ctx.ai_player:
            return 10000.0
        if game.winner is None:
            return 0.0
        return -10000.0

    # Transposition table probe.
    alpha_orig = alpha
    key = _state_key(game)
    entry = ctx.tt.get(key)
    if entry is not None and entry[0] >= depth:
        _d, val, flag = entry
        if flag == _TT_EXACT:
            return val
        if flag == _TT_LOWER and val > alpha:
            alpha = val
        elif flag == _TT_UPPER and val < beta:
            beta = val
        if alpha >= beta:
            return val

    if depth == 0:
        h = _heuristic(game, ctx.ai_player)
        ctx.tt[key] = (0, h, _TT_EXACT)
        return h

    supers = _enumerate_super_moves(game)
    if not supers:
        h = _heuristic(game, ctx.ai_player)
        ctx.tt[key] = (depth, h, _TT_EXACT)
        return h

    maximizing = (game.current_player == ctx.ai_player)
    # Order children by static eval so cutoffs trigger early.
    supers.sort(key=lambda tup: _heuristic(tup[1], ctx.ai_player), reverse=maximizing)
    if len(supers) > _INTERNAL_CAP:
        supers = supers[:_INTERNAL_CAP]

    best = float("-inf") if maximizing else float("inf")
    for _seq, g2 in supers:
        val = _minimax(g2, depth - 1, alpha, beta, ctx)
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

    # Store result with appropriate flag.
    if best <= alpha_orig:
        flag = _TT_UPPER
    elif best >= beta:
        flag = _TT_LOWER
    else:
        flag = _TT_EXACT
    # Bound table size to avoid runaway memory.
    if len(ctx.tt) < 800_000:
        ctx.tt[key] = (depth, best, flag)

    return best


def _order_supers(supers, ai_player, cap):
    supers.sort(key=lambda tup: _heuristic(tup[1], ai_player), reverse=True)
    return supers[:cap]


def _move_for_payload(seq):
    """Extract the base move (first action) for transmission to the UI."""
    if not seq:
        return None
    return seq[0]


def _iterative_deepening(root_supers, ai_player, max_depth, time_limit,
                          progress_cb=None, candidates_cb=None):
    """Search root_supers with iterative deepening. Returns (best_seq, depth_reached, nodes).

    candidates_cb, if provided, is called with a list:
      [{move, score?, rank?, kind: 'active'|'rank', depth}, ...]
    so the UI can visualize what the AI is currently searching.
    """
    ctx = _SearchCtx(ai_player, time_limit, progress_cb)
    ordering = list(range(len(root_supers)))
    best_seq = root_supers[ordering[0]][0]
    depth_done = 0
    last_candidates_emit = 0.0

    def _emit_candidates(active_idx, iter_scores, depth):
        """Throttled snapshot of (active move, top N by score so far)."""
        nonlocal last_candidates_emit
        if candidates_cb is None:
            return
        now = time.monotonic()
        if now - last_candidates_emit < 0.18:
            return
        last_candidates_emit = now
        snapshot = []
        if active_idx is not None:
            snapshot.append({
                "move": _move_for_payload(root_supers[active_idx][0]),
                "kind": "active",
                "depth": depth,
            })
        ranked = sorted(iter_scores, key=lambda x: x[1], reverse=True)[:5]
        for rank, (ix, sc) in enumerate(ranked):
            snapshot.append({
                "move": _move_for_payload(root_supers[ix][0]),
                "kind": "rank",
                "rank": rank,
                "score": sc,
                "depth": depth,
            })
        try:
            candidates_cb(snapshot)
        except Exception:
            pass

    for d in range(1, max_depth + 1):
        # If we've already used 60% of the budget, don't start a new (more
        # expensive) depth — we'd likely time out mid-iteration.
        elapsed = time.monotonic() - ctx.start
        if d > 1 and elapsed > time_limit * 0.6:
            break
        ctx.current_depth = d

        try:
            iter_scores = []
            iter_best_score = float("-inf")
            iter_best_seq = root_supers[ordering[0]][0]
            alpha = float("-inf")
            for idx in ordering:
                # Throttled "we're about to evaluate this root move" event.
                _emit_candidates(idx, iter_scores, d)
                seq, g2 = root_supers[idx]
                # After our move it's opponent's turn — minimizing side.
                score = _minimax(g2, d - 1, alpha, float("inf"), ctx)
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
            # Push a progress event at the boundary so the bar advances by depth.
            if progress_cb is not None:
                now = time.monotonic()
                try:
                    progress_cb(ctx.nodes, depth_done, now - ctx.start, time_limit)
                except Exception:
                    pass
            # And a final candidates snapshot (no active, just the ranking).
            _emit_candidates(None, iter_scores, d)
        except _Timeout:
            break

    return best_seq, depth_done, ctx.nodes


def get_ai_super_move(game, difficulty, progress_cb=None, candidates_cb=None):
    """Return list of actions for the AI to play out (place/lift + retrieves).

    progress_cb(nodes, depth, elapsed, budget) drives the thinking-progress bar.
    candidates_cb(list_of_candidates) drives the on-board ghost-sphere preview.
    """
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
        combined_reserve = game.reserve[0] + game.reserve[1]
        if combined_reserve <= 10:
            max_depth = 30
            cap = 260
            time_limit = 18.0
        elif combined_reserve <= 18:
            max_depth = 14
            cap = 240
            time_limit = 9.0
        else:
            max_depth = 10
            cap = 220
            time_limit = 6.0

    supers = _order_supers(supers, ai_player, cap)
    if len(supers) == 1:
        return supers[0][0]

    best_seq, _depth, _nodes = _iterative_deepening(
        supers, ai_player, max_depth, time_limit,
        progress_cb=progress_cb, candidates_cb=candidates_cb)
    return best_seq
