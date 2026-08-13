# qBittorrent Telegram Bot

A self-hosted, allowlist-only Telegram bot for safely adding and managing qBittorrent downloads. It supports Magnet URIs, direct `.torrent` URLs and uploaded `.torrent` files, with previews, confirmations, queue controls, notifications and optional Plex refreshes.

> Italian documentation: [README.it.md](README.it.md)

Licensed under the [MIT License](LICENSE).

## Features

- Telegram user-ID allowlist, rate limiting and callback debounce
- Magnet, URL and file input with validation and duplicate detection
- Categories, destination restrictions, size/free-space checks and blocked-file filters
- Active, paused, completed and failed views; search, pagination and torrent details
- Pause, resume, force-start, recheck and carefully confirmed deletion
- Persistent SQLite history and de-duplicated completion/error notifications
- Compact completion cards, state-aware actions and expiring removal confirmations
- Smart queue, normal/night speed profiles and server health view
- Optional, non-blocking Plex library refresh
- Rootless, read-only Docker container with healthcheck and resource limits

## Requirements

- Docker Engine with Compose v2, or Python 3.13 for manual installation
- A Telegram bot token created with [@BotFather](https://t.me/BotFather)
- qBittorrent Web UI/API reachable from the bot
- Numeric Telegram IDs for all authorized users

No third-party Python runtime packages are required.

## Screenshot

Screenshot placeholder: add a redacted menu screenshot here before the first release. Do not include usernames, chat IDs, torrent names or server addresses.

## Quick start with Docker

```bash
git clone URL_OF_THE_REPOSITORY
cd REPOSITORY_NAME
cp .env.example .env
mkdir -p data logs downloads
chmod 600 .env
# Edit .env before continuing.
docker compose config
docker compose up -d --build
docker compose ps
```

View logs with `docker compose logs -f`. Stop with `docker compose stop`.

### Connecting to qBittorrent

- **On the Docker host:** keep `QBITTORRENT_URL=http://host.docker.internal:8080`. Linux support is provided by `extra_hosts` in Compose.
- **In another container:** attach both services to a common user-defined network and use `http://qbittorrent:8080`. Remove `extra_hosts` only if it is not needed.
- **On another machine:** use its private DNS name or private-network URL. Protect traffic with a VPN or TLS reverse proxy.

Enable qBittorrent's Web UI, create dedicated credentials and restrict access to trusted networks. Never expose the Web UI directly to the public Internet.

## Telegram setup

1. Create a bot with `@BotFather` and copy the token into `TELEGRAM_BOT_TOKEN`.
2. Obtain your numeric user ID from Telegram's API or a trusted ID bot.
3. Put comma-separated numeric IDs in `ALLOWED_USER_IDS`.
4. Treat both the token and IDs as private configuration.

## Configuration

`.env.example` documents every setting. Required values are:

- `TELEGRAM_BOT_TOKEN`
- `ALLOWED_USER_IDS`
- `QBITTORRENT_URL`
- `DEFAULT_SAVE_PATH`

Credentials are required when qBittorrent authentication is enabled. Category paths are paths visible to qBittorrent. `MEDIA_ROOT_HOST` is mounted read-only into the bot only to measure free space.

Plex is disabled when `PLEX_URL` or `PLEX_TOKEN` is empty. To enable it, also set the movie and TV section IDs.

`TITLE_MAX_LENGTH` limits notification titles without renaming torrents or files. `DELETE_CONFIRMATION_SECONDS` controls destructive-confirmation expiry, and `TZ` controls displayed local times.

## Commands

- `/start` — main menu
- `/help` — usage summary
- `/status` — active downloads
- `/search name` — search torrents
- `/server` — qBittorrent, disk, RAM and load status
- `/history` — recent audited operations

## Manual installation

```bash
python3 --version
cp .env.example .env
mkdir -p data logs downloads
set -a
. ./.env
set +a
python3 bot.py
```

For a long-running Linux service, adapt [systemd/qbittorrent-telegram.service](systemd/qbittorrent-telegram.service), install the project under `/opt/qbittorrent-telegram`, place secrets in `/etc/qbittorrent-telegram.env`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now qbittorrent-telegram
sudo journalctl -u qbittorrent-telegram -f
```

## Backup and restore

Create a consistent online backup:

```bash
docker compose exec -T bot python -c 'import sqlite3; s=sqlite3.connect("/app/data/bot.sqlite3"); d=sqlite3.connect("/app/data/backup.sqlite3"); s.backup(d); d.close(); s.close()'
```

Copy `data/backup.sqlite3` to protected storage. To restore, stop the bot, preserve the current database, copy the backup to `data/bot.sqlite3`, fix ownership, then start the bot.

## Update and uninstall

Update:

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

Uninstall without deleting data:

```bash
docker compose down
```

Delete `data/` only after making a backup and only when you explicitly want to erase history and settings.

## Troubleshooting

- **Bot does not answer:** check the token, allowlist and container logs.
- **qBittorrent unreachable:** check URL, Web UI port, firewall, Docker network and credentials.
- **Unhealthy container:** check write permissions on `data/` and `logs/`, then inspect the heartbeat and SQLite files.
- **Wrong free-space value:** make `MEDIA_ROOT_HOST` point to the filesystem used for downloads.
- **Downloads use the wrong path:** category paths must match qBittorrent's own filesystem view.
- **Plex refresh fails:** verify its URL, token, section IDs and network reachability; downloads are not blocked.

## Security and responsible use

Keep `.env` mode `600`, use a dedicated qBittorrent account, keep the Web UI private, review blocked patterns and back up SQLite. Logs redact Magnet URIs and token-shaped URLs, but should still be treated as private.

Use this software only for content you are legally authorized to download and share.

See [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
