import os
import sqlite3
import sys
import time
from pathlib import Path

health = Path(os.getenv("HEALTH_FILE", "/app/data/healthy"))
database = Path(os.getenv("DATABASE_PATH", "/app/data/bot.sqlite3"))
maximum_age = int(os.getenv("HEALTH_MAX_AGE_SECONDS", "180"))

try:
    if not health.is_file() or time.time() - health.stat().st_mtime > maximum_age:
        raise RuntimeError("heartbeat assente o scaduto")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2)
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("database non integro")
    connection.close()
except (OSError, sqlite3.Error, RuntimeError) as exc:
    print(f"unhealthy: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
