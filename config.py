import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve essere un numero intero") from exc
    if value <= 0:
        raise ConfigError(f"{name} deve essere maggiore di zero")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve essere un numero intero") from exc
    if value < 0:
        raise ConfigError(f"{name} non può essere negativo")
    return value


def parse_user_ids(raw: str) -> frozenset[int]:
    try:
        values = frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise ConfigError("ALLOWED_USER_IDS deve contenere ID numerici separati da virgole") from exc
    if not values or any(value <= 0 for value in values):
        raise ConfigError("ALLOWED_USER_IDS deve contenere almeno un ID Telegram valido")
    return values


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} non configurato")
    return value


def _url(name: str) -> str:
    value = _required(name).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"{name} deve essere un URL HTTP/HTTPS valido")
    if parsed.username or parsed.password:
        raise ConfigError(f"{name} non deve contenere credenziali")
    return value


def _time(name: str, default: str) -> str:
    value = os.getenv(name, default)
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ConfigError(f"{name} deve usare il formato HH:MM")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    qbit_url: str
    qbit_username: str
    qbit_password: str
    default_save_path: str
    category_paths: dict[str, str]
    max_torrent_size_bytes: int
    max_torrent_file_bytes: int
    network_timeout: int
    database_path: Path
    unauthorized_reply: bool
    page_size: int
    monitor_interval: int
    persistent_error_checks: int
    default_queue_limit: int
    default_download_limit_kib: int
    default_upload_limit_kib: int
    night_start: str
    night_end: str
    night_download_limit_kib: int
    night_upload_limit_kib: int
    blocked_patterns: tuple[str, ...]
    plex_url: str
    plex_token: str
    plex_movie_section: str
    plex_series_section: str
    retry_attempts: int
    rate_limit_requests: int
    rate_limit_window: int
    button_debounce_seconds: int
    log_path: Path
    health_file: Path
    disk_check_path: str
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = _required("TELEGRAM_BOT_TOKEN")
        raw_ids = os.getenv("ALLOWED_USER_IDS") or os.getenv("ALLOWED_USER_ID", "")
        base = _required("DEFAULT_SAVE_PATH").rstrip("/") or "/"
        categories = {
            "film": os.getenv("CATEGORY_FILM_PATH", f"{base}/Film"),
            "serie_tv": os.getenv("CATEGORY_SERIES_PATH", f"{base}/Serie TV"),
            "musica": os.getenv("CATEGORY_MUSIC_PATH", f"{base}/Musica"),
            "altro": os.getenv("CATEGORY_OTHER_PATH", base),
        }
        if any(not path.startswith("/") for path in (base, *categories.values())):
            raise ConfigError("I percorsi di download devono essere assoluti")
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("LOG_LEVEL non valido")
        return cls(
            telegram_token=token,
            allowed_user_ids=parse_user_ids(raw_ids),
            qbit_url=_url("QBITTORRENT_URL"),
            qbit_username=os.getenv("QBITTORRENT_USERNAME", ""),
            qbit_password=os.getenv("QBITTORRENT_PASSWORD", ""),
            default_save_path=base,
            category_paths=categories,
            max_torrent_size_bytes=_positive_int("MAX_TORRENT_SIZE_GB", 100) * 1024 * 1024 * 1024,
            max_torrent_file_bytes=_positive_int("MAX_TORRENT_FILE_MB", 20) * 1024 * 1024,
            network_timeout=_positive_int("NETWORK_TIMEOUT_SECONDS", 30),
            database_path=Path(os.getenv("DATABASE_PATH", "/app/data/bot.sqlite3")),
            unauthorized_reply=os.getenv("UNAUTHORIZED_REPLY", "false").lower() in {"1", "true", "yes"},
            page_size=min(_positive_int("TORRENT_PAGE_SIZE", 8), 20),
            monitor_interval=_positive_int("MONITOR_INTERVAL_SECONDS", 60),
            persistent_error_checks=_positive_int("PERSISTENT_ERROR_CHECKS", 3),
            default_queue_limit=_positive_int("MAX_ACTIVE_DOWNLOADS", 3),
            default_download_limit_kib=_nonnegative_int("DOWNLOAD_LIMIT_KIB", 0),
            default_upload_limit_kib=_nonnegative_int("UPLOAD_LIMIT_KIB", 0),
            night_start=_time("NIGHT_MODE_START", "23:00"),
            night_end=_time("NIGHT_MODE_END", "07:00"),
            night_download_limit_kib=_nonnegative_int("NIGHT_DOWNLOAD_LIMIT_KIB", 2048),
            night_upload_limit_kib=_nonnegative_int("NIGHT_UPLOAD_LIMIT_KIB", 512),
            blocked_patterns=tuple(
                x.strip().lower() for x in os.getenv("BLOCKED_PATTERNS", "").split(",") if x.strip()
            ),
            plex_url=os.getenv("PLEX_URL", "").rstrip("/"),
            plex_token=os.getenv("PLEX_TOKEN", ""),
            plex_movie_section=os.getenv("PLEX_MOVIE_SECTION_ID", ""),
            plex_series_section=os.getenv("PLEX_SERIES_SECTION_ID", ""),
            retry_attempts=_positive_int("RETRY_ATTEMPTS", 3),
            rate_limit_requests=_positive_int("RATE_LIMIT_REQUESTS", 12),
            rate_limit_window=_positive_int("RATE_LIMIT_WINDOW_SECONDS", 60),
            button_debounce_seconds=_positive_int("BUTTON_DEBOUNCE_SECONDS", 3),
            log_path=Path(os.getenv("LOG_PATH", "/app/logs/bot.log")),
            health_file=Path(os.getenv("HEALTH_FILE", "/app/data/healthy")),
            disk_check_path=os.getenv("DISK_CHECK_PATH", base),
            log_level=log_level,
        )
