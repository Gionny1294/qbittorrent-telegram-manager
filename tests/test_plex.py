import unittest
from unittest.mock import patch

from plex_client import PlexClient


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class PlexTests(unittest.TestCase):
    def test_disabled_plex_is_non_blocking(self):
        ok, message = PlexClient().scan("Film")
        self.assertFalse(ok)
        self.assertIn("non configurato", message)

    @patch("plex_client.urllib.request.urlopen", return_value=Response())
    def test_movie_scan(self, urlopen):
        ok, _ = PlexClient("http://plex", "secret", "1", "2").scan("Film")
        self.assertTrue(ok)
        self.assertIn("/library/sections/1/refresh", urlopen.call_args.args[0].full_url)
