"""
База данных бота маленьких побед.
Использует SQLite — данные сохраняются между перезапусками.
"""

import sqlite3
import time
from pathlib import Path
from config import DB_PATH


class Storage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id             INTEGER PRIMARY KEY,
                    username            TEXT,
                    first_name          TEXT,
                    goal                TEXT,
                    utc_offset          INTEGER DEFAULT 3,
                    interval_hours      INTEGER DEFAULT 3,
                    state               TEXT DEFAULT 'setup_goal',
                    is_active           INTEGER DEFAULT 1,
                    last_notification_at REAL DEFAULT 0,
                    last_summary_at     REAL DEFAULT 0,
                    created_at          REAL NOT NULL,
                    updated_at          REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS achievements (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    text        TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS ratings (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id             INTEGER NOT NULL,
                    rating              INTEGER NOT NULL,
                    period_start        REAL NOT NULL,
                    period_end          REAL NOT NULL,
                    achievements_count  INTEGER NOT NULL,
                    created_at          REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

    # ── Пользователи ──────────────────────────────────────────────

    def get_user(self, user_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: int, username: str, first_name: str):
        now = time.time()
        with self._conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO users
                    (user_id, username, first_name, state, created_at, updated_at)
                VALUES (?, ?, ?, 'setup_goal', ?, ?)
            """, (user_id, username, first_name, now, now))

    def update_user(self, user_id: int, **fields):
        if not fields:
            return
        now = time.time()
        fields["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [user_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE users SET {set_clause} WHERE user_id = ?", values
            )

    def get_all_active_users(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE state IN ('active', 'waiting_rating')"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_users(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def count_users(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_active_users(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM users WHERE state IN ('active', 'waiting_rating') AND is_active = 1"
            ).fetchone()[0]

    # ── Достижения ────────────────────────────────────────────────

    def save_achievement(self, user_id: int, text: str) -> int:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO achievements (user_id, text, created_at) VALUES (?, ?, ?)",
                (user_id, text, now)
            )
            return cur.lastrowid

    def get_achievements(self, user_id: int, since: float = 0.0) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM achievements WHERE user_id = ? AND created_at > ? ORDER BY created_at ASC",
                (user_id, since)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_achievements(self, user_id: int, days: int = 7) -> list[dict]:
        since = time.time() - days * 86400
        return self.get_achievements(user_id, since=since)

    def count_achievements(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM achievements").fetchone()[0]

    def get_recent_all_achievements(self, limit: int = 20) -> list[dict]:
        """Для админ-панели: последние записи по всем пользователям."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT a.*, u.first_name, u.username
                FROM achievements a
                JOIN users u ON a.user_id = u.user_id
                ORDER BY a.created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ── Оценки ───────────────────────────────────────────────────

    def save_rating(self, user_id: int, rating: int, period_start: float,
                    period_end: float, achievements_count: int):
        now = time.time()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ratings
                    (user_id, rating, period_start, period_end, achievements_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, rating, period_start, period_end, achievements_count, now))

    def count_ratings(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]

    def avg_rating(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT AVG(rating) FROM ratings").fetchone()
            return round(row[0] or 0, 1)
