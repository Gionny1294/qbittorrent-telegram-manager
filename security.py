import hashlib
import logging
import re
import threading
import time
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


def is_authorized(user_id: int | None, allowed_ids: frozenset[int]) -> bool:
    return user_id is not None and user_id in allowed_ids


def safe_reference(value: str) -> str:
    """Stable reference suitable for logs; never include the supplied secret/URL."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


class RedactingFilter(logging.Filter):
    _magnet = re.compile(r"magnet:\?[^\s]+", re.IGNORECASE)
    _telegram_token = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = self._magnet.sub("magnet:<redacted>", message)
        message = self._telegram_token.sub("bot<token-redacted>", message)
        record.msg = message
        record.args = ()
        return True


class RateLimiter:
    def __init__(self, requests, window_seconds):
        self.requests, self.window = requests, window_seconds
        self.events = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.requests:
                return False
            events.append(now)
            return True


class InteractionGuard:
    def __init__(self, seconds):
        self.seconds, self.seen, self.lock = seconds, {}, threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            previous = self.seen.get(key, 0)
            if now - previous < self.seconds:
                return False
            self.seen[key] = now
            if len(self.seen) > 1000:
                self.seen = {k: value for k, value in self.seen.items() if now - value < self.seconds}
            return True


def configure_logging(log_path=None, level="INFO") -> None:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers = [logging.StreamHandler()]
    if log_path:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"))
    for handler in handlers:
        handler.addFilter(RedactingFilter())
        handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(getattr(logging, level, logging.INFO))
