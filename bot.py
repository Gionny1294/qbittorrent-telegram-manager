import datetime
import logging
import os
import signal
import threading
import urllib.parse
import uuid
from contextlib import suppress

from config import Settings
from database import Database
from plex_client import PlexClient
from qbittorrent_client import DuplicateTorrent, QBitClient, QBitError
from security import InteractionGuard, RateLimiter, configure_logging, is_authorized, safe_reference
from telegram_api import TelegramAPI, TelegramError
from torrent_manager import (
    ERROR_STATES,
    details_text,
    enforce_queue,
    filter_torrents,
    in_night_window,
    paginate,
    system_metrics,
)
from ui import (
    CATEGORIES,
    category_keyboard,
    confirm_keyboard,
    delete_confirmation,
    human_size,
    main_menu,
    settings_keyboard,
    torrent_actions,
    torrent_list_keyboard,
)
from validators import (
    ValidationError,
    extract_input,
    magnet_hash,
    safe_destination,
    sanitize_filename,
    torrent_metadata,
    validate_files,
)

log = logging.getLogger("bot")
GROUP_LABELS = {
    "active": "Download attivi",
    "paused": "Torrent in pausa",
    "completed": "Torrent completati",
    "error": "Torrent in errore",
}


class Bot:
    def __init__(self, settings, telegram=None, qbit=None, database=None, plex=None):
        self.settings = settings
        self.telegram = telegram or TelegramAPI(settings.telegram_token, settings.network_timeout)
        self.qbit = qbit or QBitClient(
            settings.qbit_url,
            settings.qbit_username,
            settings.qbit_password,
            settings.network_timeout,
            settings.retry_attempts,
        )
        self.db = database or Database(settings.database_path)
        self.plex = plex or PlexClient(
            settings.plex_url,
            settings.plex_token,
            settings.plex_movie_section,
            settings.plex_series_section,
            settings.network_timeout,
            settings.retry_attempts,
        )
        self.db.sync_users(settings.allowed_user_ids)
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window)
        self.interaction_guard = InteractionGuard(settings.button_debounce_seconds)

    def touch_health(self):
        self.settings.health_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings.health_file.touch()

    def authorized(self, user_id, chat_id=None):
        allowed = is_authorized(user_id, self.settings.allowed_user_ids)
        if not allowed:
            log.warning("Accesso negato all'utente %s", user_id)
            if self.settings.unauthorized_reply and chat_id:
                self.telegram.send(chat_id, "Operazione non disponibile.")
        return allowed

    @property
    def allowed_roots(self):
        return tuple(set(self.settings.category_paths.values()) | {self.settings.default_save_path})

    def queue_limit(self):
        return max(1, int(self.db.get_setting("queue_limit", self.settings.default_queue_limit)))

    def mode(self):
        return self.db.get_setting("speed_mode", "auto")

    def effective_limits(self, now=None):
        mode = self.mode()
        night = mode == "night" or (
            mode == "auto"
            and in_night_window(
                now or datetime.datetime.now(), self.settings.night_start, self.settings.night_end
            )
        )
        prefix = "night" if night else "normal"
        defaults = (
            (self.settings.night_download_limit_kib, self.settings.night_upload_limit_kib)
            if night
            else (self.settings.default_download_limit_kib, self.settings.default_upload_limit_kib)
        )
        return (
            int(self.db.get_setting(f"{prefix}_download_kib", defaults[0])),
            int(self.db.get_setting(f"{prefix}_upload_kib", defaults[1])),
            prefix,
        )

    def preview(self, chat_id, user_id, kind, source, filename="download.torrent", content=None):
        filename = sanitize_filename(filename)
        if kind == "magnet":
            info_hash = magnet_hash(source)
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(source).query)
            name, tracker, size, files = (
                query.get("dn", ["Metadati non ancora disponibili"])[0],
                query.get("tr", ["Non disponibile"])[0],
                0,
                [],
            )
        else:
            content = (
                content
                if content is not None
                else self.telegram.download_url(source, self.settings.max_torrent_file_bytes)
            )
            metadata = torrent_metadata(content)
            info_hash, name, tracker, size, files = (
                metadata[key] for key in ("hash", "name", "tracker", "size", "files")
            )
            validate_files(files, self.settings.blocked_patterns)
            if size > self.settings.max_torrent_size_bytes:
                raise ValidationError(f"Torrent troppo grande: {human_size(size)}")
        if self.qbit.contains(info_hash):
            raise DuplicateTorrent("Questo torrent è già presente in qBittorrent")
        operation_id = uuid.uuid4().hex[:16]
        payload = {
            "source": source,
            "filename": filename,
            "hash": info_hash,
            "name": name,
            "tracker": tracker,
            "size": size,
            "files": files,
        }
        if content is not None:
            pending_dir = self.settings.database_path.parent / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            pending_file = pending_dir / f"{operation_id}.torrent"
            pending_file.write_bytes(content)
            payload["pending_file"] = str(pending_file)
        self.db.create_operation(operation_id, user_id, kind, payload)
        self.telegram.send(chat_id, "Scegli la categoria:", category_keyboard(operation_id))

    def show_preview(self, callback, operation_id, category):
        user_id, chat_id = callback["from"]["id"], callback["message"]["chat"]["id"]
        operation = self.db.claim_operation(operation_id, user_id)
        if not operation or category not in CATEGORIES:
            self.telegram.answer_callback(callback["id"], "Operazione scaduta")
            return
        path = safe_destination(self.settings.category_paths[category], self.allowed_roots)
        payload = operation["payload"] | {"category": category}
        self.db.finish_operation(operation_id, "replaced")
        next_id = uuid.uuid4().hex[:16]
        self.db.create_operation(next_id, user_id, operation["kind"], payload)
        free = self.qbit.disk_free(self.settings.disk_check_path)
        files = payload.get("files", [])
        file_text = (
            ", ".join(files[:5]) + (f" (+{len(files) - 5})" if len(files) > 5 else "")
            if files
            else "non disponibili"
        )
        text = (
            f"Anteprima torrent\nNome: {payload['name']}\nHash: {payload['hash']}\nTracker: {payload['tracker']}\n"
            f"Categoria: {CATEGORIES[category]}\nDestinazione: {path}\nDimensione: {human_size(payload['size']) if payload['size'] else 'non disponibile'}\n"
            f"File: {file_text}\nSpazio libero: {human_size(free) if free is not None else 'non disponibile'}"
        )
        self.telegram.send(chat_id, text, confirm_keyboard(next_id))
        self.telegram.answer_callback(callback["id"])

    def confirm(self, callback, operation_id):
        user_id, chat_id = callback["from"]["id"], callback["message"]["chat"]["id"]
        operation = self.db.claim_operation(operation_id, user_id)
        if not operation:
            self.telegram.answer_callback(callback["id"], "Operazione scaduta")
            return
        payload = operation["payload"]
        try:
            path = safe_destination(self.settings.category_paths[payload["category"]], self.allowed_roots)
            free, size = self.qbit.disk_free(self.settings.disk_check_path), payload.get("size", 0)
            if free is not None and size and free < size:
                self.db.finish_operation(operation_id, "no_space")
                self.telegram.send(chat_id, "Spazio libero insufficiente.")
                return
            if self.qbit.contains(payload["hash"]):
                raise DuplicateTorrent("Questo torrent è già presente in qBittorrent")
            category = CATEGORIES[payload["category"]]
            if operation["kind"] == "magnet":
                self.qbit.add_url(payload["source"], path, category)
            else:
                pending = payload.get("pending_file")
                if pending:
                    with open(pending, "rb") as handle:
                        content = handle.read()
                else:
                    content = self.telegram.download_url(
                        payload["source"], self.settings.max_torrent_file_bytes
                    )
                self.qbit.add_file(payload["filename"], content, path, category)
                if pending:
                    with suppress(OSError):
                        os.unlink(pending)
        except Exception:
            self.db.release_operation(operation_id)
            raise
        self.db.finish_operation(operation_id, "confirmed")
        self.db.record(user_id, "added", payload["hash"], category)
        log.info("Torrent aggiunto ref=%s", safe_reference(payload["hash"]))
        self.telegram.send(chat_id, f"Torrent aggiunto: {payload['name']}", main_menu())
        self.telegram.answer_callback(callback["id"])

    def list_torrents(self, chat_id, group="active", page=0, query=None, user_id=None):
        callback_group = group
        actual_group = group
        if query and user_id:
            self.db.set_setting(f"search_query:{user_id}", query)
            callback_group, actual_group = "search", None
        elif group == "search":
            query = self.db.get_setting(f"search_query:{user_id}", "")
            actual_group = None
        torrents = filter_torrents(self.qbit.torrents(), actual_group, query)
        items, page, pages = paginate(torrents, page, self.settings.page_size)
        title = f"{GROUP_LABELS.get(actual_group, 'Ricerca torrent')} — {len(torrents)} risultati"
        self.telegram.send(chat_id, title, torrent_list_keyboard(items, callback_group, page, pages))

    def show_details(self, chat_id, info_hash):
        torrent = self.qbit.torrent(info_hash)
        self.telegram.send(
            chat_id,
            details_text(torrent, self.qbit.properties(info_hash), self.qbit.trackers(info_hash)),
            torrent_actions(info_hash),
        )

    def torrent_action(self, user_id, chat_id, action, info_hash):
        torrent = self.qbit.torrent(info_hash)
        self.qbit.action(action, info_hash)
        self.db.record(user_id, action, info_hash, torrent.get("name"))
        self.telegram.send(chat_id, f"Azione eseguita: {action}")

    def remove_torrent(self, user_id, chat_id, info_hash, files):
        torrent = self.qbit.torrent(info_hash)
        save_path = torrent.get("save_path", "")
        safe_destination(save_path, self.allowed_roots)
        self.qbit.delete(info_hash, files)
        self.db.record(user_id, "deleted_files" if files else "deleted", info_hash, torrent.get("name"))
        self.telegram.send(
            chat_id, "Torrent e file rimossi." if files else "Torrent rimosso; file conservati.", main_menu()
        )

    def server_status(self, chat_id):
        torrents, transfer = self.qbit.torrents(), self.qbit.transfer_info()
        free = self.qbit.disk_free(self.settings.disk_check_path)
        ram, load = system_metrics()
        text = (
            f"qBittorrent: connesso ({self.qbit.version()})\nTorrent: {len(torrents)}\n"
            f"Download: {human_size(transfer.get('dl_info_speed', 0))}/s\nUpload: {human_size(transfer.get('up_info_speed', 0))}/s\n"
            f"Spazio libero: {human_size(free) if free is not None else 'non disponibile'}\nRAM: {ram}\nCarico 1/5/15m: {load}"
        )
        self.telegram.send(chat_id, text, main_menu())

    def history(self, chat_id):
        rows = self.db.history(20)
        lines = [
            f"{datetime.datetime.fromtimestamp(row['created_at']):%d/%m %H:%M} — {row['user_id']} — {row['action']} — {row['detail'] or row['torrent_hash'] or '-'}"
            for row in rows
        ]
        self.telegram.send(chat_id, "Cronologia\n" + ("\n".join(lines) if lines else "Nessuna operazione."))

    def show_settings(self, chat_id):
        download, upload, effective = self.effective_limits()
        text = (
            f"Coda: {self.queue_limit()} download\nModalità: {self.mode()} (attiva: {effective})\n"
            f"Limite download: {download} KiB/s (0=illimitato)\nLimite upload: {upload} KiB/s\n"
            f"Notte: {self.settings.night_start}–{self.settings.night_end}"
        )
        self.telegram.send(chat_id, text, settings_keyboard(self.queue_limit(), self.mode()))

    def scan_plex(self, user_id, chat_id, info_hash, automatic=False):
        torrent = self.qbit.torrent(info_hash)
        ok, message = self.plex.scan(torrent.get("category", ""))
        self.db.record(user_id, "plex_scan_ok" if ok else "plex_scan_failed", info_hash, message)
        if not automatic:
            self.telegram.send(chat_id, message)
        return ok

    def monitor_once(self):
        torrents = self.qbit.torrents()
        initialized = self.db.get_setting("monitor_initialized", "0") == "1"
        for torrent in torrents:
            info_hash, state = torrent.get("hash"), torrent.get("state", "")
            if not info_hash:
                continue
            complete = float(torrent.get("progress", 0)) >= 0.999999
            if complete and not self.db.notification_sent(info_hash, "completed"):
                if initialized:
                    for user_id in self.settings.allowed_user_ids:
                        self.telegram.send(
                            user_id,
                            f"✅ Download completato\n{torrent.get('name', 'Torrent')}",
                            torrent_actions(info_hash),
                        )
                    if torrent.get("category") in {"Film", "Serie TV"}:
                        self.scan_plex(0, 0, info_hash, True)
                self.db.mark_notification(info_hash, "completed")
            if state in ERROR_STATES:
                key = f"error_count:{info_hash}"
                count = int(self.db.get_setting(key, 0)) + 1
                self.db.set_setting(key, count)
                if count >= self.settings.persistent_error_checks and not self.db.notification_sent(
                    info_hash, "error"
                ):
                    for user_id in self.settings.allowed_user_ids:
                        self.telegram.send(
                            user_id,
                            f"⚠️ Errore persistente\n{torrent.get('name', 'Torrent')}",
                            torrent_actions(info_hash),
                        )
                    self.db.mark_notification(info_hash, "error")
            else:
                self.db.set_setting(f"error_count:{info_hash}", 0)
        if not initialized:
            self.db.set_setting("monitor_initialized", "1")
        managed = set(filter(None, self.db.get_setting("queue_managed_hashes", "").split(",")))
        changes = enforce_queue(self.qbit, torrents, self.queue_limit(), managed)
        for info_hash, action in changes:
            self.db.record(0, action, info_hash, "gestione automatica coda")
            if action == "queue_paused":
                managed.add(info_hash)
            elif action == "queue_resumed":
                managed.discard(info_hash)
        existing = {item.get("hash") for item in torrents}
        self.db.set_setting("queue_managed_hashes", ",".join(sorted(managed & existing)))
        download, upload, mode = self.effective_limits()
        last = self.db.get_setting("applied_limits", "")
        current = f"{download}:{upload}:{mode}"
        if current != last:
            self.qbit.set_limits(download, upload)
            self.db.set_setting("applied_limits", current)
        self.touch_health()

    def monitor_loop(self):
        while not self.stop_event.is_set():
            try:
                self.monitor_once()
            except Exception:
                log.exception("Errore monitor periodico")
            self.stop_event.wait(self.settings.monitor_interval)

    def handle_message(self, message):
        chat_id, user_id = message.get("chat", {}).get("id"), message.get("from", {}).get("id")
        if not chat_id or not self.authorized(user_id, chat_id):
            return
        if not self.rate_limiter.allow(user_id):
            self.telegram.send(chat_id, "Troppe richieste. Attendi qualche secondo.")
            return
        text = (message.get("text") or message.get("caption") or "").strip()
        if text.startswith("/start"):
            self.telegram.send(chat_id, "Benvenuto. Scegli un’operazione.", main_menu())
            return
        if text.startswith("/help"):
            self.telegram.send(
                chat_id,
                "Comandi: /start, /help, /status, /search nome, /history, /server. Sono supportati Magnet URL, URL e file .torrent.",
                main_menu(),
            )
            return
        if text.startswith("/history"):
            self.history(chat_id)
            return
        if text.startswith("/server"):
            self.server_status(chat_id)
            return
        if text.startswith("/search "):
            self.list_torrents(chat_id, None, 0, text.split(maxsplit=1)[1], user_id)
            return
        menu_groups = {
            "⬇️ Attivi": "active",
            "⏸ In pausa": "paused",
            "✅ Completati": "completed",
            "⚠️ Errori": "error",
        }
        if text.startswith("/status"):
            self.list_torrents(chat_id, "active", user_id=user_id)
            return
        if text in menu_groups:
            self.list_torrents(chat_id, menu_groups[text], user_id=user_id)
            return
        if text == "🔎 Cerca":
            self.telegram.send(chat_id, "Usa /search seguito dal nome, per esempio: /search ubuntu")
            return
        if text == "➕ Aggiungi":
            self.telegram.send(
                chat_id, "Invia un Magnet URL, un URL diretto .torrent o allega un file .torrent."
            )
            return
        if text == "💾 Disco":
            free = self.qbit.disk_free(self.settings.disk_check_path)
            self.telegram.send(
                chat_id,
                f"Spazio libero: {human_size(free) if free is not None else 'non disponibile'}",
                main_menu(),
            )
            return
        if text == "⚙️ Impostazioni":
            self.show_settings(chat_id)
            return
        document = message.get("document")
        if document:
            filename = sanitize_filename(document.get("file_name", "download.torrent"))
            if not filename.lower().endswith(".torrent"):
                raise ValidationError("Il file deve avere estensione .torrent")
            self.preview(
                chat_id,
                user_id,
                "file",
                "",
                filename,
                self.telegram.download(document["file_id"], self.settings.max_torrent_file_bytes),
            )
            return
        kind, source = extract_input(text)
        self.preview(
            chat_id, user_id, kind, source, source.rsplit("/", 1)[-1] if kind == "url" else "download.torrent"
        )

    def handle_callback(self, callback):
        user_id, chat_id = (
            callback.get("from", {}).get("id"),
            callback.get("message", {}).get("chat", {}).get("id"),
        )
        if not self.authorized(user_id, chat_id):
            return
        data = callback.get("data", "")
        if not self.rate_limiter.allow(user_id):
            self.telegram.answer_callback(callback["id"], "Troppe richieste")
            return
        if not self.interaction_guard.allow((user_id, data)):
            self.telegram.answer_callback(callback["id"], "Operazione già ricevuta")
            return
        parts = data.split(":")
        if parts[0] == "noop":
            self.telegram.answer_callback(callback["id"])
            return
        if len(parts) == 3 and parts[0] == "cat":
            self.show_preview(callback, parts[1], parts[2])
        elif len(parts) == 2 and parts[0] == "confirm":
            self.confirm(callback, parts[1])
        elif len(parts) == 2 and parts[0] == "cancel":
            self.db.finish_operation(parts[1], "cancelled")
            self.telegram.answer_callback(callback["id"], "Annullato")
        elif len(parts) == 3 and parts[0] == "list":
            self.list_torrents(chat_id, parts[1], int(parts[2]), user_id=user_id)
            self.telegram.answer_callback(callback["id"])
        elif len(parts) == 2 and parts[0] == "detail":
            self.show_details(chat_id, parts[1])
            self.telegram.answer_callback(callback["id"])
        elif len(parts) == 3 and parts[0] == "act":
            self.torrent_action(user_id, chat_id, parts[1], parts[2])
            self.telegram.answer_callback(callback["id"])
        elif len(parts) == 3 and parts[0] == "delete":
            kind, info_hash = parts[1], parts[2]
            if kind == "torrent":
                self.telegram.send(
                    chat_id,
                    "Confermi la rimozione del torrent? I file saranno conservati.",
                    delete_confirmation(info_hash, False),
                )
            elif kind == "torrent_confirm":
                self.remove_torrent(user_id, chat_id, info_hash, False)
            elif kind == "files1":
                self.telegram.send(
                    chat_id,
                    "Attenzione: verranno eliminati anche i file. Prima conferma.",
                    delete_confirmation(info_hash, True, True),
                )
            elif kind == "files2":
                self.telegram.send(
                    chat_id,
                    "Conferma finale: eliminare definitivamente torrent e file?",
                    {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "ELIMINA DEFINITIVAMENTE",
                                    "callback_data": f"delete:files_confirm:{info_hash}",
                                }
                            ]
                        ]
                    },
                )
            elif kind == "files_confirm":
                self.remove_torrent(user_id, chat_id, info_hash, True)
            self.telegram.answer_callback(callback["id"])
        elif len(parts) == 2 and parts[0] == "plex":
            self.scan_plex(user_id, chat_id, parts[1])
            self.telegram.answer_callback(callback["id"])
        elif len(parts) == 3 and parts[0] == "setting":
            if parts[1] == "queue":
                self.db.set_setting("queue_limit", max(1, self.queue_limit() + int(parts[2])))
            elif parts[1] == "mode":
                self.db.set_setting(
                    "speed_mode", {"auto": "normal", "normal": "night", "night": "auto"}[self.mode()]
                )
            elif parts[1] == "limits":
                profile, direction = parts[2].split("_")
                key = f"{profile}_{'download' if direction == 'dl' else 'upload'}_kib"
                current = int(self.db.get_setting(key, 0))
                self.db.set_setting(key, {0: 1024, 1024: 2048, 2048: 5120}.get(current, 0))
                self.db.set_setting("applied_limits", "")
            self.show_settings(chat_id)
            self.telegram.answer_callback(callback["id"])

    def run(self):
        me = self.telegram.call("getMe")
        log.info("Bot @%s avviato", me.get("username"))
        self.monitor_thread = threading.Thread(target=self.monitor_loop, name="torrent-monitor", daemon=True)
        self.monitor_thread.start()
        offset = None
        while not self.stop_event.is_set():
            try:
                data = {"timeout": 20, "allowed_updates": '["message","callback_query"]'}
                if offset is not None:
                    data["offset"] = offset
                for update in self.telegram.call("getUpdates", data):
                    offset = update["update_id"] + 1
                    try:
                        if "message" in update:
                            self.handle_message(update["message"])
                        elif "callback_query" in update:
                            self.handle_callback(update["callback_query"])
                    except (ValidationError, DuplicateTorrent, QBitError, TelegramError) as exc:
                        target = (
                            (update.get("message") or update.get("callback_query", {}).get("message", {}))
                            .get("chat", {})
                            .get("id")
                        )
                        if target:
                            self.telegram.send(target, str(exc))
                    except Exception:
                        log.exception("Errore aggiornamento")
                self.touch_health()
            except Exception:
                if not self.stop_event.is_set():
                    log.exception("Errore polling; nuovo tentativo tra 10 secondi")
                    self.stop_event.wait(10)

    def stop(self, *_):
        self.stop_event.set()

    def close(self):
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=self.settings.network_timeout + 2)
        self.db.close()


if __name__ == "__main__":
    settings = Settings.from_env()
    configure_logging(settings.log_path, settings.log_level)
    bot = Bot(settings)
    signal.signal(signal.SIGTERM, bot.stop)
    signal.signal(signal.SIGINT, bot.stop)
    try:
        bot.run()
    finally:
        bot.close()
