import json
import sqlite3
import threading
import time
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self):
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, authorized INTEGER NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    action TEXT NOT NULL, torrent_hash TEXT, detail TEXT, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    torrent_hash TEXT NOT NULL, event TEXT NOT NULL, sent_at INTEGER NOT NULL,
                    PRIMARY KEY(torrent_hash, event)
                );
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO schema_migrations VALUES (1, unixepoch());
            """)

    def sync_users(self, allowed_ids):
        now = int(time.time())
        with self.lock, self.connection:
            self.connection.execute("UPDATE users SET authorized=0")
            self.connection.executemany(
                "INSERT INTO users VALUES (?,1,?) ON CONFLICT(telegram_id) DO UPDATE SET authorized=1",
                ((user_id, now) for user_id in allowed_ids),
            )

    def create_operation(self, operation_id, user_id, kind, payload):
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO operations VALUES (?,?,?,?,?,?)",
                (operation_id, user_id, kind, json.dumps(payload), "pending", int(time.time())),
            )

    def operation(self, operation_id, user_id):
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM operations WHERE id=? AND user_id=? AND status='pending'",
                (operation_id, user_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def claim_operation(self, operation_id, user_id):
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT * FROM operations WHERE id=? AND user_id=? AND status='pending'",
                (operation_id, user_id),
            ).fetchone()
            if not row:
                return None
            updated = self.connection.execute(
                "UPDATE operations SET status='processing' WHERE id=? AND status='pending'", (operation_id,)
            ).rowcount
            if updated != 1:
                return None
            result = dict(row)
            result["payload"] = json.loads(result["payload"])
            return result

    def finish_operation(self, operation_id, status):
        with self.lock, self.connection:
            self.connection.execute("UPDATE operations SET status=? WHERE id=?", (status, operation_id))

    def release_operation(self, operation_id):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE operations SET status='pending' WHERE id=? AND status='processing'", (operation_id,)
            )

    def record(self, user_id, action, torrent_hash=None, detail=None):
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO history(user_id,action,torrent_hash,detail,created_at) VALUES (?,?,?,?,?)",
                (user_id, action, torrent_hash, detail, int(time.time())),
            )

    def counts(self):
        with self.lock:
            return {
                "users": self.connection.execute("SELECT COUNT(*) FROM users WHERE authorized=1").fetchone()[
                    0
                ],
                "history": self.connection.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            }

    def history(self, limit=20):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

    def get_setting(self, key, default=None):
        with self.lock:
            row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO settings VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, str(value), int(time.time())),
            )

    def notification_sent(self, torrent_hash, event):
        with self.lock:
            return (
                self.connection.execute(
                    "SELECT 1 FROM notifications WHERE torrent_hash=? AND event=?", (torrent_hash, event)
                ).fetchone()
                is not None
            )

    def mark_notification(self, torrent_hash, event):
        with self.lock, self.connection:
            return (
                self.connection.execute(
                    "INSERT OR IGNORE INTO notifications VALUES (?,?,?)",
                    (torrent_hash, event, int(time.time())),
                ).rowcount
                == 1
            )

    def close(self):
        with self.lock:
            self.connection.close()
