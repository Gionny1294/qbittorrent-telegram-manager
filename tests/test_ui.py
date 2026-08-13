import tempfile
import unittest

from bot import Bot
from database import Database
from plex_client import PlexClient
from tests.fakes import FakeQBit, FakeTelegram, settings, torrent
from torrent_manager import completion_text, details_text, is_complete, normalized_state
from ui import torrent_actions


def labels(keyboard):
    return {button["text"] for row in keyboard["inline_keyboard"] for button in row}


class DynamicKeyboardTests(unittest.TestCase):
    def test_active_has_pause_not_resume(self):
        result = labels(torrent_actions(torrent("downloading", 0.5)))
        self.assertIn("⏸ Pausa", result)
        self.assertNotIn("▶️ Riprendi", result)

    def test_paused_has_resume_not_pause(self):
        result = labels(torrent_actions(torrent("stoppedDL", 0.5)))
        self.assertIn("▶️ Riprendi", result)
        self.assertNotIn("⏸ Pausa", result)

    def test_completed_has_only_relevant_actions(self):
        result = labels(torrent_actions(torrent("uploading", 1)))
        for unwanted in ("🔄 Aggiorna", "⏸ Pausa", "▶️ Riprendi", "⏩ Forza avvio", "🔁 Riprova"):
            self.assertNotIn(unwanted, result)
        self.assertIn("ℹ️ Dettagli", result)
        self.assertIn("📂 Altri completati", result)
        self.assertIn("🗑 Gestisci rimozione", result)

    def test_plex_button_requires_configured_matching_library(self):
        completed = torrent("uploading", 1)
        self.assertNotIn("🎬 Scansiona Plex", labels(torrent_actions(completed, False)))
        self.assertIn("🎬 Scansiona Plex", labels(torrent_actions(completed, True)))
        plex = PlexClient("http://plex", "token", "1", "")
        self.assertTrue(plex.can_scan("Film"))
        self.assertFalse(plex.can_scan("Serie TV"))


class RenderingTests(unittest.TestCase):
    def test_long_unicode_and_html_title_is_safely_shortened(self):
        item = torrent("uploading", 1) | {"name": "🎬 <Titolo & speciale> " + "界" * 100}
        text = completion_text(item, "UTC", 30, completed_at=0)
        self.assertIn("&lt;Titolo &amp;", text)
        self.assertIn("…", text)
        self.assertNotIn("<Titolo", text)

    def test_seeding_is_completed(self):
        item = torrent("stalledUP", 0.75) | {"amount_left": 100}
        self.assertTrue(is_complete(item))
        self.assertEqual(normalized_state(item), "completed")

    def test_all_supported_qbittorrent_states_are_classified(self):
        expected = {
            "error": "error",
            "missingFiles": "error",
            "uploading": "completed",
            "stoppedUP": "completed",
            "pausedUP": "completed",
            "queuedUP": "completed",
            "stalledUP": "completed",
            "checkingUP": "completed",
            "forcedUP": "completed",
            "downloading": "downloading",
            "forcedDL": "downloading",
            "stalledDL": "downloading",
            "stoppedDL": "paused",
            "pausedDL": "paused",
            "metaDL": "queued",
            "queuedDL": "queued",
            "checkingDL": "queued",
            "checkingResumeData": "queued",
            "allocating": "queued",
            "moving": "queued",
            "unknown": "unknown",
        }
        for state, classification in expected.items():
            with self.subTest(state=state):
                self.assertEqual(normalized_state(torrent(state, 0.5)), classification)

    def test_multi_file_total_size_is_used_in_completion(self):
        item = torrent("uploading", 1) | {"size": 1, "total_size": 5 * 1024**3}
        text = completion_text(item, "UTC", 70, completed_at=0)
        self.assertIn("5,00 GB", text)

    def test_missing_fields_do_not_create_empty_rows(self):
        self.assertEqual(details_text({}), "")
        text = completion_text({"name": "Test", "hash": "a" * 40}, "UTC", 70, completed_at=0)
        self.assertNotIn("Categoria", text)
        self.assertNotIn("non disponibile", text.lower())

    def test_completion_time_uses_configured_timezone(self):
        text = completion_text(torrent("uploading", 1), "Europe/Rome", 70, completed_at=0)
        self.assertIn("Completato alle 01:00", text)


class RemovalFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = settings(self.temp.name)
        self.settings.allowed_user_ids = frozenset({10, 20})
        self.telegram = FakeTelegram()
        self.qbit = FakeQBit([torrent("uploading", 1)])
        self.bot = Bot(self.settings, self.telegram, self.qbit, Database(self.settings.database_path))

    def tearDown(self):
        self.bot.db.close()
        self.temp.cleanup()

    @staticmethod
    def callback(user_id, data, callback_id="callback"):
        return {
            "id": callback_id,
            "from": {"id": user_id},
            "message": {"message_id": 7, "chat": {"id": 10}},
            "data": data,
        }

    def open_menu(self):
        self.bot.show_removal_menu(self.callback(10, "remove:" + "a" * 40), "a" * 40)
        keyboard = self.telegram.edited[-1][3]
        return keyboard["inline_keyboard"][0][0]["callback_data"].rsplit(":", 1)[1]

    def test_files_require_second_confirmation(self):
        operation_id = self.open_menu()
        self.bot.handle_delete(self.callback(10, f"delete:files:{operation_id}"), "files", operation_id)
        self.assertEqual(self.qbit.deletions, [])
        keyboard = self.telegram.edited[-1][3]
        final_data = keyboard["inline_keyboard"][0][0]["callback_data"]
        final_id = final_data.rsplit(":", 1)[1]
        self.bot.handle_delete(self.callback(10, final_data), "confirm", final_id)
        self.assertEqual(self.qbit.deletions, [("a" * 40, True)])

    def test_other_user_cannot_confirm(self):
        operation_id = self.open_menu()
        self.bot.handle_delete(self.callback(20, f"delete:keep:{operation_id}"), "keep", operation_id)
        self.assertEqual(self.qbit.deletions, [])

    def test_expired_callback_does_not_delete(self):
        operation_id = self.open_menu()
        with self.bot.db.connection:
            self.bot.db.connection.execute(
                "UPDATE operations SET created_at=created_at-1000 WHERE id=?", (operation_id,)
            )
        self.bot.handle_delete(self.callback(10, f"delete:keep:{operation_id}"), "keep", operation_id)
        self.assertEqual(self.qbit.deletions, [])

    def test_repeated_click_does_not_delete_twice(self):
        operation_id = self.open_menu()
        callback = self.callback(10, f"delete:keep:{operation_id}")
        self.bot.handle_delete(callback, "keep", operation_id)
        self.bot.handle_delete(callback, "keep", operation_id)
        self.assertEqual(self.qbit.deletions, [("a" * 40, False)])


class PersistentNotificationTests(unittest.TestCase):
    def test_completion_is_not_repeated_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = settings(directory)
            item = torrent("uploading", 1)
            first_telegram = FakeTelegram()
            first = Bot(configured, first_telegram, FakeQBit([item]), Database(configured.database_path))
            first.db.set_setting("monitor_initialized", "1")
            first.monitor_once()
            first.close()
            second_telegram = FakeTelegram()
            second = Bot(configured, second_telegram, FakeQBit([item]), Database(configured.database_path))
            second.monitor_once()
            second.close()
            self.assertEqual(sum("Download completato" in text for _, text, _ in first_telegram.sent), 1)
            self.assertFalse(any("Download completato" in text for _, text, _ in second_telegram.sent))
