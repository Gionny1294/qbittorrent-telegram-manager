from pathlib import Path
from types import SimpleNamespace


def settings(tmpdir):
    return SimpleNamespace(
        telegram_token="test",
        allowed_user_ids=frozenset({10}),
        qbit_url="http://qbit",
        qbit_username="",
        qbit_password="",
        network_timeout=1,
        database_path=Path(tmpdir) / "bot.sqlite3",
        plex_url="",
        plex_token="",
        plex_movie_section="",
        plex_series_section="",
        category_paths={
            "film": "/downloads/Film",
            "serie_tv": "/downloads/Serie",
            "musica": "/downloads/Musica",
            "altro": "/downloads/Altro",
        },
        default_save_path="/downloads",
        max_torrent_file_bytes=1024,
        max_torrent_size_bytes=10**9,
        blocked_patterns=(),
        unauthorized_reply=False,
        page_size=2,
        monitor_interval=60,
        persistent_error_checks=2,
        default_queue_limit=3,
        default_download_limit_kib=0,
        default_upload_limit_kib=0,
        night_start="23:00",
        night_end="07:00",
        night_download_limit_kib=100,
        night_upload_limit_kib=50,
        retry_attempts=1,
        rate_limit_requests=100,
        rate_limit_window=60,
        button_debounce_seconds=3,
        log_path=Path(tmpdir) / "bot.log",
        health_file=Path(tmpdir) / "healthy",
        disk_check_path="/downloads",
        log_level="INFO",
    )


class FakeTelegram:
    def __init__(self):
        self.sent, self.answers = [], []

    def send(self, chat_id, text, keyboard=None):
        self.sent.append((chat_id, text, keyboard))

    def answer_callback(self, callback_id, text=""):
        self.answers.append((callback_id, text))


class FakeQBit:
    def __init__(self, torrents=None):
        self.items = torrents or []
        self.actions, self.deletions, self.limits = [], [], []

    def torrents(self, torrent_filter=None):
        return self.items

    def torrent(self, info_hash):
        return next(item for item in self.items if item["hash"] == info_hash)

    def action(self, action, info_hash):
        self.actions.append((action, info_hash))

    def delete(self, info_hash, files=False):
        self.deletions.append((info_hash, files))

    def set_limits(self, down, up):
        self.limits.append((down, up))

    def disk_free(self, path):
        return 10**9

    def properties(self, info_hash):
        return {}

    def trackers(self, info_hash):
        return []


def torrent(state="downloading", progress=0.5):
    return {
        "hash": "a" * 40,
        "name": "Test torrent",
        "state": state,
        "progress": progress,
        "save_path": "/downloads/Film",
        "category": "Film",
        "size": 100,
        "downloaded": 50,
        "dlspeed": 10,
        "eta": 5,
        "ratio": 0.2,
    }
