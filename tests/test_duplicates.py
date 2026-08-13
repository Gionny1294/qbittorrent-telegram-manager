import unittest
import urllib.error
from unittest.mock import patch

from qbittorrent_client import QBitClient, QBitError


class FakeClient(QBitClient):
    def __init__(self, torrents):
        self._torrents = torrents

    def torrents(self, torrent_filter=None):
        return self._torrents


class DuplicateTests(unittest.TestCase):
    def test_hash_match_is_case_insensitive(self):
        client = FakeClient([{"hash": "ABC123"}])
        self.assertTrue(client.contains("abc123"))
        self.assertFalse(client.contains("def456"))

    @patch(
        "qbittorrent_client.urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("offline")
    )
    def test_unavailable_qbittorrent_is_reported_safely(self, _open):
        client = QBitClient("http://qbittorrent:8080", timeout=1, retries=1)
        with self.assertRaisesRegex(QBitError, "non riuscito"):
            client.login()
