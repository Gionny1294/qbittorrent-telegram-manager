import json
import urllib.error
import urllib.parse
import urllib.request


class TelegramError(RuntimeError):
    pass


class TelegramAPI:
    def __init__(self, token, timeout=30):
        self.api = f"https://api.telegram.org/bot{token}"
        self.file_api = f"https://api.telegram.org/file/bot{token}"
        self.timeout = timeout

    def call(self, method, data=None):
        encoded = urllib.parse.urlencode(data or {}).encode()
        try:
            # The Telegram API base is a fixed HTTPS URL.
            with urllib.request.urlopen(  # nosec B310
                urllib.request.Request(f"{self.api}/{method}", data=encoded), timeout=self.timeout
            ) as response:
                result = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TelegramError("Telegram non raggiungibile") from exc
        if not result.get("ok"):
            raise TelegramError("Telegram non ha accettato la richiesta")
        return result["result"]

    def send(self, chat_id, text, keyboard=None):
        chunks = self._chunks(str(text), 4000)
        result = None
        for index, chunk in enumerate(chunks):
            data = {"chat_id": chat_id, "text": chunk}
            if keyboard and index == len(chunks) - 1:
                data["reply_markup"] = json.dumps(keyboard)
            result = self.call("sendMessage", data)
        return result

    @staticmethod
    def _chunks(text, limit):
        if not text:
            return [""]
        chunks = []
        while len(text) > limit:
            split = text.rfind("\n", 0, limit + 1)
            if split <= 0:
                split = limit
            chunks.append(text[:split])
            text = text[split:].lstrip("\n")
        chunks.append(text)
        return chunks

    def answer_callback(self, callback_id, text=""):
        return self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def download(self, file_id, max_bytes):
        info = self.call("getFile", {"file_id": file_id})
        try:
            # The Telegram file API base is a fixed HTTPS URL.
            with urllib.request.urlopen(  # nosec B310
                f"{self.file_api}/{info['file_path']}", timeout=self.timeout
            ) as response:
                content = response.read(max_bytes + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TelegramError("Download del file da Telegram non riuscito") from exc
        if len(content) > max_bytes:
            raise TelegramError("Il file .torrent supera il limite configurato")
        return content

    def download_url(self, url, max_bytes):
        request = urllib.request.Request(url, headers={"User-Agent": "qBittorrent-Telegram/2"})
        try:
            # direct_torrent_url restricts user input to HTTP(S).
            with urllib.request.urlopen(  # nosec B310
                request, timeout=self.timeout
            ) as response:
                if response.headers.get_content_type() not in {
                    "application/x-bittorrent",
                    "application/octet-stream",
                } and not url.lower().endswith(".torrent"):
                    raise TelegramError("L’URL non restituisce un file .torrent")
                content = response.read(max_bytes + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TelegramError("URL del torrent non raggiungibile") from exc
        if len(content) > max_bytes:
            raise TelegramError("Il file .torrent supera il limite configurato")
        return content
