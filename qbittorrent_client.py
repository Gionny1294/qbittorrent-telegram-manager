import json
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.cookiejar import CookieJar


class QBitError(RuntimeError):
    pass


class DuplicateTorrent(QBitError):
    pass


class QBitClient:
    def __init__(self, url, username=None, password=None, timeout=30, retries=3):
        self.url = url
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.retries = retries
        self.lock = threading.RLock()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def _open(self, request, retry=False):
        attempts = self.retries if retry else 1
        for attempt in range(attempts):
            try:
                with self.lock:
                    return self.opener.open(request, timeout=self.timeout)
            except (urllib.error.URLError, TimeoutError):
                if attempt + 1 >= attempts:
                    raise
                time.sleep(min(2**attempt, 8))

    def _post(self, path, fields, files=None):
        if files:
            boundary = uuid.uuid4().hex
            body = bytearray()
            for name, value in fields.items():
                body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
                )
            for field, filename, content in files:
                body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: application/x-bittorrent\r\n\r\n'.encode()
                )
                body.extend(content)
                body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode())
            request = urllib.request.Request(
                self.url + path,
                data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
        else:
            request = urllib.request.Request(self.url + path, data=urllib.parse.urlencode(fields).encode())
        try:
            with self._open(request) as response:
                return response.read().decode(errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                raise DuplicateTorrent("Torrent già presente") from exc
            raise QBitError(f"qBittorrent ha risposto con errore HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise QBitError("qBittorrent non raggiungibile") from exc

    def _get_json(self, path, query=None):
        url = self.url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        try:
            with self._open(url, retry=True) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QBitError("Risposta qBittorrent non disponibile o non valida") from exc

    def login(self):
        if self.username and self.password:
            if (
                self._post(
                    "/api/v2/auth/login", {"username": self.username, "password": self.password}
                ).strip()
                != "Ok."
            ):
                raise QBitError("Credenziali qBittorrent non accettate")
        else:
            try:
                self._open(self.url + "/api/v2/app/version", retry=True).close()
            except (urllib.error.URLError, TimeoutError) as exc:
                raise QBitError("Accesso qBittorrent non riuscito") from exc

    def torrents(self, torrent_filter=None):
        self.login()
        return self._get_json("/api/v2/torrents/info", {"filter": torrent_filter} if torrent_filter else None)

    def contains(self, info_hash):
        return any(item.get("hash", "").lower() == info_hash.lower() for item in self.torrents())

    def ensure_category(self, category, save_path):
        self.login()
        categories = self._get_json("/api/v2/torrents/categories")
        if category not in categories:
            try:
                self._post("/api/v2/torrents/createCategory", {"category": category, "savePath": save_path})
            except DuplicateTorrent as exc:
                raise QBitError("Impossibile creare la categoria qBittorrent") from exc

    def add_url(self, url, save_path, category):
        self.login()
        self.ensure_category(category, save_path)
        self._check(
            self._post("/api/v2/torrents/add", {"urls": url, "savepath": save_path, "category": category})
        )

    def add_file(self, filename, content, save_path, category):
        self.login()
        self.ensure_category(category, save_path)
        fields = {"savepath": save_path, "category": category}
        self._check(self._post("/api/v2/torrents/add", fields, [("torrents", filename, content)]))

    @staticmethod
    def _check(result):
        if result.strip() in {"", "Ok."}:
            return
        raise QBitError("qBittorrent non ha accettato il torrent")

    def transfer_info(self):
        self.login()
        return self._get_json("/api/v2/transfer/info")

    def torrent(self, info_hash):
        matches = [item for item in self.torrents() if item.get("hash", "").lower() == info_hash.lower()]
        if not matches:
            raise QBitError("Torrent non trovato")
        return matches[0]

    def properties(self, info_hash):
        self.login()
        return self._get_json("/api/v2/torrents/properties", {"hash": info_hash})

    def trackers(self, info_hash):
        self.login()
        return self._get_json("/api/v2/torrents/trackers", {"hash": info_hash})

    def files(self, info_hash):
        self.login()
        return self._get_json("/api/v2/torrents/files", {"hash": info_hash})

    def action(self, action, info_hash):
        endpoints = {"pause": "stop", "resume": "start", "force": "setForceStart", "retry": "recheck"}
        if action not in endpoints:
            raise QBitError("Azione torrent non valida")
        fields = {"hashes": info_hash}
        if action == "force":
            fields["value"] = "true"
        self.login()
        self._check(self._post(f"/api/v2/torrents/{endpoints[action]}", fields))

    def delete(self, info_hash, delete_files=False):
        self.login()
        self._check(
            self._post(
                "/api/v2/torrents/delete", {"hashes": info_hash, "deleteFiles": str(delete_files).lower()}
            )
        )

    def set_limits(self, download_kib, upload_kib):
        self.login()
        self._check(self._post("/api/v2/transfer/setDownloadLimit", {"limit": int(download_kib) * 1024}))
        self._check(self._post("/api/v2/transfer/setUploadLimit", {"limit": int(upload_kib) * 1024}))

    def version(self):
        self.login()
        try:
            with self._open(self.url + "/api/v2/app/version", retry=True) as response:
                return response.read().decode().strip()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise QBitError("Versione qBittorrent non disponibile") from exc

    @staticmethod
    def disk_free(path):
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return None
