"""
Pylos - Database layer (SQLite by default, Postgres if DATABASE_URL set).

Tracks:
  - pylos_leaderboard:  PvAI win/loss/tie counts per difficulty
  - pylos_players:      PvP ELO rankings
  - pylos_pvp_games:    history of PvP results

Tables are prefixed `pylos_` so they can share a Postgres DB with other apps.
"""
import os
import sqlite3


_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
_USE_PG = bool(_DATABASE_URL)
_PH = "%s" if _USE_PG else "?"

if _USE_PG:
    import psycopg2


def _db_conn():
    if _USE_PG:
        return psycopg2.connect(_DATABASE_URL)
    return sqlite3.connect("pylos_leaderboard.db")


def _init_db():
    try:
        conn = _db_conn()
        cur = conn.cursor()
        if _USE_PG:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_leaderboard (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    ties INTEGER NOT NULL DEFAULT 0,
                    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_players (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    elo INTEGER NOT NULL DEFAULT 1000,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    ties INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_pvp_games (
                    id SERIAL PRIMARY KEY,
                    p1_name TEXT NOT NULL,
                    p2_name TEXT NOT NULL,
                    p1_display TEXT NOT NULL,
                    p2_display TEXT NOT NULL,
                    p1_reserve INTEGER NOT NULL,
                    p2_reserve INTEGER NOT NULL,
                    winner_name TEXT,
                    p1_elo_before INTEGER NOT NULL,
                    p2_elo_before INTEGER NOT NULL,
                    p1_elo_after INTEGER NOT NULL,
                    p2_elo_after INTEGER NOT NULL,
                    p1_elo_change INTEGER NOT NULL,
                    p2_elo_change INTEGER NOT NULL,
                    played_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_leaderboard (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    ties INTEGER NOT NULL DEFAULT 0,
                    submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    elo INTEGER NOT NULL DEFAULT 1000,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    ties INTEGER NOT NULL DEFAULT 0,
                    games_played INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pylos_pvp_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    p1_name TEXT NOT NULL,
                    p2_name TEXT NOT NULL,
                    p1_display TEXT NOT NULL,
                    p2_display TEXT NOT NULL,
                    p1_reserve INTEGER NOT NULL,
                    p2_reserve INTEGER NOT NULL,
                    winner_name TEXT,
                    p1_elo_before INTEGER NOT NULL,
                    p2_elo_before INTEGER NOT NULL,
                    p1_elo_after INTEGER NOT NULL,
                    p2_elo_after INTEGER NOT NULL,
                    p1_elo_change INTEGER NOT NULL,
                    p2_elo_change INTEGER NOT NULL,
                    played_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB init error: {e}")
    _consolidate_leaderboard()


def _consolidate_leaderboard():
    """Merge duplicate (name, difficulty) rows left over from the old insert-only logic."""
    try:
        conn = _db_conn()
        cur = conn.cursor()
        if _USE_PG:
            cur.execute("""
                WITH agg AS (
                    SELECT MIN(id) AS keep_id,
                           name, difficulty,
                           SUM(wins)   AS total_wins,
                           SUM(losses) AS total_losses
                    FROM pylos_leaderboard
                    GROUP BY name, difficulty
                    HAVING COUNT(*) > 1
                )
                UPDATE pylos_leaderboard lb
                SET wins = agg.total_wins, losses = agg.total_losses
                FROM agg WHERE lb.id = agg.keep_id
            """)
        else:
            cur.execute("""
                UPDATE pylos_leaderboard
                SET wins   = (SELECT SUM(b.wins)   FROM pylos_leaderboard b WHERE b.name = pylos_leaderboard.name AND b.difficulty = pylos_leaderboard.difficulty),
                    losses = (SELECT SUM(b.losses)  FROM pylos_leaderboard b WHERE b.name = pylos_leaderboard.name AND b.difficulty = pylos_leaderboard.difficulty)
                WHERE id IN (
                    SELECT MIN(id) FROM pylos_leaderboard GROUP BY name, difficulty HAVING COUNT(*) > 1
                )
            """)
        cur.execute("""
            DELETE FROM pylos_leaderboard
            WHERE id NOT IN (
                SELECT MIN(id) FROM pylos_leaderboard GROUP BY name, difficulty
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Leaderboard consolidation error: {e}")


def _calc_elo(ra, rb, outcome_a, k=32):
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    new_ra = round(ra + k * (outcome_a - ea))
    new_rb = round(rb + k * ((1 - outcome_a) - (1 - ea)))
    return new_ra, new_rb


def _record_pvp_game(room):
    if len(room["players"]) < 2:
        return
    p0, p1 = room["players"][0], room["players"][1]
    game = room["game"]
    p0_key, p1_key = p0["name"].lower(), p1["name"].lower()
    p0_reserve, p1_reserve = game.reserve[0], game.reserve[1]
    winner = game.winner
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT name, elo FROM pylos_players WHERE name IN ({_PH},{_PH})",
            (p0_key, p1_key)
        )
        elo_map = {r[0]: r[1] for r in cur.fetchall()}
        ra, rb = elo_map.get(p0_key, 1000), elo_map.get(p1_key, 1000)
        outcome = 1.0 if winner == 0 else (0.0 if winner == 1 else 0.5)
        new_ra, new_rb = _calc_elo(ra, rb, outcome)
        winner_key = None if winner is None else (p0_key if winner == 0 else p1_key)
        p0_w, p0_l, p0_t = (1,0,0) if winner==0 else ((0,1,0) if winner==1 else (0,0,1))
        p1_w, p1_l, p1_t = (1,0,0) if winner==1 else ((0,1,0) if winner==0 else (0,0,1))
        if _USE_PG:
            upsert = (
                f"INSERT INTO pylos_players (name,display_name,elo,wins,losses,ties,games_played) "
                f"VALUES ({_PH},{_PH},{_PH},{_PH},{_PH},{_PH},1) "
                f"ON CONFLICT (name) DO UPDATE SET "
                f"display_name=EXCLUDED.display_name,elo=EXCLUDED.elo,"
                f"wins=pylos_players.wins+EXCLUDED.wins,losses=pylos_players.losses+EXCLUDED.losses,"
                f"ties=pylos_players.ties+EXCLUDED.ties,games_played=pylos_players.games_played+1"
            )
            cur.execute(upsert, (p0_key, p0["name"], new_ra, p0_w, p0_l, p0_t))
            cur.execute(upsert, (p1_key, p1["name"], new_rb, p1_w, p1_l, p1_t))
        else:
            upsert = (
                "INSERT INTO pylos_players (name,display_name,elo,wins,losses,ties,games_played) "
                "VALUES (?,?,?,?,?,?,1) "
                "ON CONFLICT(name) DO UPDATE SET "
                "display_name=excluded.display_name,elo=excluded.elo,"
                "wins=pylos_players.wins+excluded.wins,losses=pylos_players.losses+excluded.losses,"
                "ties=pylos_players.ties+excluded.ties,games_played=pylos_players.games_played+1"
            )
            cur.execute(upsert, (p0_key, p0["name"], new_ra, p0_w, p0_l, p0_t))
            cur.execute(upsert, (p1_key, p1["name"], new_rb, p1_w, p1_l, p1_t))
        cur.execute(
            f"INSERT INTO pylos_pvp_games "
            f"(p1_name,p2_name,p1_display,p2_display,p1_reserve,p2_reserve,winner_name,"
            f"p1_elo_before,p2_elo_before,p1_elo_after,p2_elo_after,p1_elo_change,p2_elo_change) "
            f"VALUES ({','.join([_PH]*13)})",
            (p0_key, p1_key, p0["name"], p1["name"], p0_reserve, p1_reserve, winner_key,
             ra, rb, new_ra, new_rb, new_ra-ra, new_rb-rb)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"PvP record error: {e}")


_init_db()
