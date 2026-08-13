import datetime
import html
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ui import human_size

ERROR_STATES = {"error", "missingFiles"}
PAUSED_STATES = {"stoppedDL", "stoppedUP", "pausedDL", "pausedUP"}
DOWNLOAD_STATES = {"downloading", "forcedDL", "stalledDL"}
WAITING_STATES = {"metaDL", "queuedDL", "checkingDL", "checkingResumeData", "allocating", "moving"}
COMPLETE_STATES = {"uploading", "stoppedUP", "pausedUP", "queuedUP", "stalledUP", "checkingUP", "forcedUP"}
KNOWN_STATES = ERROR_STATES | PAUSED_STATES | DOWNLOAD_STATES | WAITING_STATES | COMPLETE_STATES


def is_complete(torrent):
    state = torrent.get("state", "unknown")
    if state in ERROR_STATES:
        return False
    if state in COMPLETE_STATES:
        return True
    try:
        progress = float(torrent.get("progress", 0) or 0)
        left = torrent.get("amount_left")
        size = float(torrent.get("total_size", torrent.get("size", 0)) or 0)
        return progress >= 0.999999 or (left is not None and int(left) == 0 and size > 0)
    except (TypeError, ValueError):
        return False


def normalized_state(torrent):
    state = torrent.get("state", "unknown")
    if state in ERROR_STATES:
        return "error"
    if is_complete(torrent):
        return "completed"
    if state in {"stoppedDL", "pausedDL"}:
        return "paused"
    if state in WAITING_STATES:
        return "queued"
    if state in DOWNLOAD_STATES:
        return "downloading"
    return "unknown"


def supported_actions(torrent):
    normalized = normalized_state(torrent)
    actions = {"details", "remove"}
    if normalized != "completed":
        actions.add("refresh")
    if normalized == "downloading":
        actions.add("pause")
    elif normalized == "paused":
        actions.add("resume")
    elif normalized == "queued" and torrent.get("state") == "queuedDL":
        actions.add("force")
    elif normalized == "error" and torrent.get("state") in ERROR_STATES:
        actions.add("retry")
    elif normalized == "completed":
        actions.add("completed_list")
    return actions


def torrent_group(torrent):
    state = normalized_state(torrent)
    return {"downloading": "active", "queued": "active", "unknown": "active"}.get(state, state)


def filter_torrents(torrents, group=None, query=None):
    result = torrents
    if group == "downloading":
        result = [torrent for torrent in result if normalized_state(torrent) == "downloading"]
    elif group:
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


def _value(value):
    return value not in {None, "", "unknown", "Non disponibile"}


def details_text(torrent, properties=None, trackers=None):
    properties = properties or {}
    tracker = next(
        (
            item.get("url")
            for item in (trackers or [])
            if item.get("url", "").startswith(("http://", "https://"))
        ),
        "",
    )
    complete = is_complete(torrent)
    rows = [("<b>Nome:</b>", torrent.get("name")), ("<b>Stato:</b>", torrent.get("state"))]
    size = torrent.get("total_size", torrent.get("size"))
    if size:
        rows.append(("<b>Dimensione:</b>", human_size(size)))
    if not complete:
        if torrent.get("progress") is not None:
            rows.append(("<b>Avanzamento:</b>", f"{float(torrent['progress'] or 0) * 100:.1f}%"))
        if torrent.get("downloaded"):
            rows.append(("<b>Scaricato:</b>", human_size(torrent["downloaded"])))
        if torrent.get("dlspeed"):
            rows.append(("<b>Velocità download:</b>", f"{human_size(torrent['dlspeed'])}/s"))
        if torrent.get("eta") is not None:
            rows.append(("<b>Tempo stimato:</b>", eta_text(torrent["eta"])))
    elif torrent.get("state") in {"uploading", "stalledUP", "forcedUP", "queuedUP"}:
        if torrent.get("upspeed"):
            rows.append(("<b>Velocità upload:</b>", f"{human_size(torrent['upspeed'])}/s"))
        if torrent.get("ratio") is not None:
            rows.append(("<b>Ratio:</b>", f"{float(torrent['ratio']):.2f}"))
    for label, value in (
        ("<b>Categoria:</b>", torrent.get("category")),
        ("<b>Tracker:</b>", tracker),
        ("<b>Cartella:</b>", torrent.get("save_path") or properties.get("save_path")),
    ):
        if _value(value):
            rows.append((label, value))
    return "\n".join(f"{label} {html.escape(str(value))}" for label, value in rows if label and _value(value))


_TECHNICAL = re.compile(
    r"\b(?:2160p|1080p|720p|480p|web[ ._-]?dl|webrip|bluray|brrip|hdrip|dvdrip|x26[45]|h[ ._-]?26[45]|hevc|av1|hdr10?|dolby[ ._-]?vision|dts(?:-hd)?|aac\d?(?:\.\d)?|ac3|eac3|ita(?:lian)?|eng(?:lish)?|multi(?:sub)?|repack|proper)\b.*$",
    re.IGNORECASE,
)


def display_title(name, max_length=70):
    title = str(name or "Torrent").strip()
    title = re.sub(r"\.(?:mkv|mp4|avi|mov|m4v|ts)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\[[^\]]{1,40}\]|\([^)]{1,30}\)$", " ", title)
    title = re.sub(r"[._]+", " ", title)
    title = _TECHNICAL.sub("", title)
    title = re.sub(r"\s+", " ", title).strip(" -–—._") or str(name or "Torrent").strip()
    if len(title) > max_length:
        title = title[: max(1, max_length - 1)].rstrip() + "…"
    return title


def completion_text(torrent, timezone="UTC", max_title_length=70, completed_at=None):
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    timestamp = completed_at
    if timestamp is None:
        timestamp = torrent.get("completion_on") or datetime.datetime.now().timestamp()
    when = datetime.datetime.fromtimestamp(float(timestamp), zone)
    rows = [
        "✅ <b>Download completato</b>",
        f"🎬 {html.escape(display_title(torrent.get('name'), max_title_length))}",
    ]
    size = torrent.get("total_size", torrent.get("size"))
    if size:
        rows.append(f"💾 {human_size(size, 2, True, True)}")
    if torrent.get("category"):
        rows.append(f"📁 {html.escape(str(torrent['category']))}")
    rows.append(f"🕒 Completato alle {when:%H:%M}")
    return "\n".join(rows)


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
    downloading = [item for item in torrents if normalized_state(item) == "downloading"]
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
