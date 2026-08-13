import os
import unittest
from unittest.mock import patch

from config import ConfigError, Settings, parse_user_ids


class ConfigTests(unittest.TestCase):
    def test_multiple_allowed_ids(self):
        self.assertEqual(parse_user_ids("10, 20"), frozenset({10, 20}))

    def test_invalid_allowed_ids(self):
        with self.assertRaises(ConfigError):
            parse_user_ids("not-a-number")

    def test_required_token(self):
        with (
            patch.dict(os.environ, {"ALLOWED_USER_IDS": "10"}, clear=True),
            self.assertRaises(ConfigError),
        ):
            Settings.from_env()

    def test_loads_environment(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ALLOWED_USER_IDS": "10,20",
            "DEFAULT_SAVE_PATH": "/downloads",
            "QBITTORRENT_URL": "http://qbittorrent:8080",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.allowed_user_ids, frozenset({10, 20}))
        self.assertEqual(settings.category_paths["film"], "/downloads/Film")

    def test_invalid_qbittorrent_url_is_rejected(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ALLOWED_USER_IDS": "10",
            "DEFAULT_SAVE_PATH": "/downloads",
            "QBITTORRENT_URL": "not-an-url",
        }
        with patch.dict(os.environ, env, clear=True), self.assertRaises(ConfigError):
            Settings.from_env()

    def test_invalid_timezone_is_rejected(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ALLOWED_USER_IDS": "10",
            "DEFAULT_SAVE_PATH": "/downloads",
            "QBITTORRENT_URL": "http://qbittorrent:8080",
            "TZ": "Mars/Olympus",
        }
        with patch.dict(os.environ, env, clear=True), self.assertRaises(ConfigError):
            Settings.from_env()
