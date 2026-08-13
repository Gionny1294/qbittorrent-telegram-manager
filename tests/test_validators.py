import hashlib
import unittest

from validators import ValidationError, magnet_hash, safe_destination, sanitize_filename, torrent_metadata


class MagnetTests(unittest.TestCase):
    def test_valid_hex_hash(self):
        value = "0123456789abcdef0123456789abcdef01234567"
        self.assertEqual(magnet_hash(f"magnet:?xt=urn:btih:{value}&dn=Test"), value)

    def test_invalid_magnet(self):
        with self.assertRaises(ValidationError):
            magnet_hash("magnet:?dn=no-hash")


class TorrentMetadataTests(unittest.TestCase):
    def test_extracts_hash_name_and_size(self):
        info = b"d6:lengthi12e4:name4:teste"
        data = b"d8:announce15:http://track.er4:info" + info + b"e"
        metadata = torrent_metadata(data)
        self.assertEqual(metadata["hash"], hashlib.sha1(info, usedforsecurity=False).hexdigest())
        self.assertEqual(metadata["name"], "test")
        self.assertEqual(metadata["size"], 12)


class PathSafetyTests(unittest.TestCase):
    def test_filename_is_sanitized(self):
        self.assertEqual(sanitize_filename("../../unsafe?.torrent"), "unsafe_.torrent")

    def test_destination_must_be_below_allowed_root(self):
        self.assertEqual(safe_destination("/downloads/movies", ("/downloads",)), "/downloads/movies")
        with self.assertRaises(ValidationError):
            safe_destination("/etc", ("/downloads",))
