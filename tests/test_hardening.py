import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from database import Database
from security import InteractionGuard, RateLimiter
from telegram_api import TelegramAPI


class FakeTelegram(TelegramAPI):
    def __init__(self):
        self.calls = []

    def call(self, method, data=None):
        self.calls.append((method, data))
        return {"message_id": len(self.calls)}


class HardeningTests(unittest.TestCase):
    def test_long_telegram_messages_are_split(self):
        telegram = FakeTelegram()
        telegram.send(10, "x" * 9000, {"inline_keyboard": []})
        self.assertEqual(len(telegram.calls), 3)
        self.assertNotIn("reply_markup", telegram.calls[0][1])
        self.assertIn("reply_markup", telegram.calls[-1][1])

    def test_rate_limiter(self):
        limiter = RateLimiter(2, 60)
        self.assertTrue(limiter.allow(10))
        self.assertTrue(limiter.allow(10))
        self.assertFalse(limiter.allow(10))

    def test_button_debounce(self):
        guard = InteractionGuard(60)
        self.assertTrue(guard.allow((10, "pause")))
        self.assertFalse(guard.allow((10, "pause")))

    def test_operation_can_only_be_claimed_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.create_operation("id", 10, "magnet", {"hash": "abc"})
            self.assertIsNotNone(database.claim_operation("id", 10))
            self.assertIsNone(database.claim_operation("id", 10))
            database.close()


@unittest.skipUnless(shutil.which("docker"), "Docker non disponibile")
class DockerConfigurationTests(unittest.TestCase):
    def test_compose_configuration_is_valid(self):
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["BOT_ENV_FILE"] = ".env.example"
        result = subprocess.run(
            ["docker", "compose", "--env-file", ".env.example", "config", "--quiet"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
