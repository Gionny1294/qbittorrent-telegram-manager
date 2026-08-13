import datetime
import os

from ui import human_size

ERROR_STATES = {"error", "missingFiles", "unknown"}
PAUSED_STATES = {"stoppedDL", "stoppedUP", "pausedDL", "pausedUP"}
ACTIVE_STATES = {"downloading", "metaDL", "forcedDL", "stalledDL", "checkingDL", "queuedDL", "allocating"}


def torrent_group(torrent):
    state = torrent.get("state", "unknown")
    if state in ERROR_STATES:
        return "error"
    if state in PAUSED_STATES:
        return "paused"
    if float(torrent.get("progress", 0)) >= 0.999999:
        return "completed"
    return "active"


def filter_torrents(torrents, group=None, query=None):
    result = torrents
    if group:
        result = [torrent for torrent in result if torrent_group(torrent) == group]
    if query:
        lowered = query.lower()
        result = [torrent for torrent in result if lowered in torrent.get("name", "").lower()]
    return sorted(result, key=lambda item: item.get("name", "").lower())


def paginate(items, page, page_size):
    pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, pages - 1))
    return items[page * page_size : (page + 1) * page_size], page, pages


def eta_text(seconds):
    if seconds is None or int(seconds) < 0 or int(seconds) >= 8640000:
        return "∞"
    return str(datetime.timedelta(seconds=int(seconds)))


def details_text(torrent, properties=None, trackers=None):
    properties = properties or {}
    tracker = next(
        (
            item.get("url")
            for item in (trackers or [])
            if item.get("url", "").startswith(("http://", "https://"))
        ),
        "Non disponibile",
    )
    return (
        f"Nome: {torrent.get('name', 'Torrent')}\n"
        f"Avanzamento: {float(torrent.get('progress', 0)) * 100:.1f}%\n"
        f"Stato: {torrent.get('state', 'unknown')}\n"
        f"Dimensione: {human_size(torrent.get('size', torrent.get('total_size', 0)))}\n"
        f"Scaricato: {human_size(torrent.get('downloaded', 0))}\n"
        f"Velocità: {human_size(torrent.get('dlspeed', 0))}/s\n"
        f"Tempo stimato: {eta_text(torrent.get('eta'))}\n"
        f"Ratio: {float(torrent.get('ratio', 0)):.2f}\n"
        f"Categoria: {torrent.get('category') or 'Nessuna'}\n"
        f"Tracker: {tracker}\n"
        f"Cartella: {torrent.get('save_path', properties.get('save_path', 'Non disponibile'))}"
    )


def system_metrics():
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in handle}
        total, available = values["MemTotal"], values["MemAvailable"]
        ram = f"{human_size(total - available)} / {human_size(total)}"
    except (OSError, KeyError, ValueError):
        ram = "non disponibile"
    try:
        load = ", ".join(f"{value:.2f}" for value in os.getloadavg())
    except OSError:
        load = "non disponibile"
    return ram, load


def in_night_window(now, start, end):
    current = now.time()
    start_time = datetime.time.fromisoformat(start)
    end_time = datetime.time.fromisoformat(end)
    return (
        start_time <= current < end_time
        if start_time < end_time
        else current >= start_time or current < end_time
    )


def enforce_queue(qbit, torrents, limit, managed_paused=None):
    managed_paused = set(managed_paused or ())
    downloading = [
        item for item in torrents if torrent_group(item) == "active" and item.get("state") != "queuedDL"
    ]
    changed = []
    for torrent in downloading[limit:]:
        qbit.action("pause", torrent["hash"])
        changed.append((torrent["hash"], "queue_paused"))
    available = max(0, limit - min(len(downloading), limit))
    queued = [
        item
        for item in torrents
        if item.get("hash") in managed_paused
        and item.get("state") in PAUSED_STATES
        and float(item.get("progress", 0)) < 1
    ]
    for torrent in queued[:available]:
        qbit.action("resume", torrent["hash"])
        changed.append((torrent["hash"], "queue_resumed"))
    return changed
