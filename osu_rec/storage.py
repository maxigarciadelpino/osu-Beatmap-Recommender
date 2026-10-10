import sqlite3, json, threading
from datetime import datetime, timezone
from . import config as C
from .mods import mods_str

SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
  score_id INTEGER PRIMARY KEY, user_id INTEGER, ended_at TEXT,
  beatmap_id INTEGER, title TEXT, mods TEXT, accuracy REAL, passed INTEGER,
  misses INTEGER, max_combo INTEGER, pp REAL, rank TEXT,
  stars REAL, bpm REAL, session_id INTEGER, raw TEXT);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, started_at TEXT);
"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path=None):
        self.db = sqlite3.connect(str(path or C.DB_FILE), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self._migrate()

    def _migrate(self):
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(sessions)")}
        if "user_id" not in cols:
            self.db.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER")
            self.db.commit()

    def new_session(self, user_id, ts=None):
        with self.lock:
            cur = self.db.execute("INSERT INTO sessions(user_id, started_at) VALUES (?,?)",
                                  (user_id, ts or now_iso()))
            self.db.commit()
            return cur.lastrowid

    def last_session(self, user_id):
        with self.lock:
            row = self.db.execute("SELECT MAX(id) FROM sessions WHERE user_id=?", (user_id,)).fetchone()
        return row[0]

    def add_play(self, s, session_id):
        bm = s.get("beatmap") or {}
        bs = s.get("beatmapset") or {}
        title = f"{bs.get('artist', '?')} - {bs.get('title', '?')} [{bm.get('version', '?')}]"
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO plays VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], s["user_id"], s["ended_at"], s["beatmap_id"], title, mods_str(s),
                 s["accuracy"], int(bool(s["passed"])), s.get("statistics", {}).get("miss", 0),
                 s.get("max_combo"), s.get("pp"), s.get("rank"), bm.get("difficulty_rating"),
                 bm.get("bpm"), session_id, json.dumps(s)))
            self.db.commit()
            return cur.rowcount == 1

    def session_plays(self, session_id):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM plays WHERE session_id=? ORDER BY ended_at", (session_id,)).fetchall()
        return [dict(r) for r in rows]
