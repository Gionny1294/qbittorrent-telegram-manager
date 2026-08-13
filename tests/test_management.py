import tempfile
import unittest

from bot import Bot
from database import Database
from tests.fakes import FakeQBit, FakeTelegram, settings, torrent
from torrent_manager import paginate


class TorrentManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = settings(self.temp.name)
        self.telegram = FakeTelegram()
        self.qbit = FakeQBit([torrent()])
        self.bot = Bot(self.settings, self.telegram, self.qbit, Database(self.settings.database_path))

    def tearDown(self):
        self.temp.cleanup()

    def test_pause_and_resume(self):
        self.bot.torrent_action(10, 10, "pause", "a" * 40)
        self.qbit.items[0]["state"] = "stoppedDL"
        self.bot.torrent_action(10, 10, "resume", "a" * 40)
        self.assertEqual(self.qbit.actions, [("pause", "a" * 40), ("resume", "a" * 40)])

    def test_delete_torrent_and_files(self):
        self.bot.remove_torrent(10, 10, "a" * 40, False)
        self.bot.remove_torrent(10, 10, "a" * 40, True)
        self.assertEqual(self.qbit.deletions, [("a" * 40, False), ("a" * 40, True)])

    def test_unauthorized_callback_does_nothing(self):
        callback = {
            "id": "c",
            "from": {"id": 999},
            "message": {"chat": {"id": 999}},
            "data": f"act:pause:{'a' * 40}",
        }
        self.bot.handle_callback(callback)
        self.assertEqual(self.qbit.actions, [])

    def test_completion_notification_is_not_duplicated(self):
        self.qbit.items[0]["progress"] = 1
        self.qbit.items[0]["state"] = "uploading"
        self.bot.db.set_setting("monitor_initialized", "1")
        self.bot.monitor_once()
        self.bot.monitor_once()
        completed = [message for _, message, _ in self.telegram.sent if "Download completato" in message]
        self.assertEqual(len(completed), 1)

    def test_speed_limits_applied(self):
        self.bot.db.set_setting("speed_mode", "normal")
        self.bot.db.set_setting("normal_download_kib", 2048)
        self.bot.db.set_setting("normal_upload_kib", 512)
        self.bot.monitor_once()
        self.assertEqual(self.qbit.limits[-1], (2048, 512))

    def test_graceful_shutdown_closes_database(self):
        self.bot.stop()
        self.bot.close()
        self.assertTrue(self.bot.stop_event.is_set())


class PaginationTests(unittest.TestCase):
    def test_pages_are_bounded(self):
        items, page, pages = paginate(list(range(5)), 1, 2)
        self.assertEqual(items, [2, 3])
        self.assertEqual((page, pages), (1, 3))
