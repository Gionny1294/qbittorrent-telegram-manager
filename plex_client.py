import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("plex")


class PlexClient:
    def __init__(self, url=None, token=None, movie_section="", series_section="", timeout=30, retries=3):
        self.url, self.token = url or "", token or ""
        self.sections = {"Film": movie_section, "Serie TV": series_section}
        self.timeout = timeout
        self.retries = retries

    @property
    def configured(self):
        return bool(self.url and self.token)

    def can_scan(self, category):
        return self.configured and bool(self.sections.get(category, ""))

    def scan(self, category):
        section = self.sections.get(category, "")
        if not self.can_scan(category):
            return False, "Plex non configurato per questa categoria"
        url = f"{self.url}/library/sections/{urllib.parse.quote(section)}/refresh?X-Plex-Token={urllib.parse.quote(self.token)}"
        for attempt in range(self.retries):
            try:
                # Settings restricts this base URL to HTTP(S).
                with urllib.request.urlopen(  # nosec B310
                    urllib.request.Request(url, method="GET"), timeout=self.timeout
                ) as response:
                    if response.status not in {200, 201}:
                        return False, f"Plex HTTP {response.status}"
                return True, "Scansione Plex avviata"
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt + 1 >= self.retries:
                    log.warning("Scansione Plex non riuscita: %s", type(exc).__name__)
                    return False, "Plex non raggiungibile"
                time.sleep(min(2**attempt, 8))
