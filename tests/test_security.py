import unittest

from security import is_authorized


class AuthorizationTests(unittest.TestCase):
    def test_only_configured_ids_are_allowed(self):
        allowed = frozenset({10, 20})
        self.assertTrue(is_authorized(10, allowed))
        self.assertFalse(is_authorized(30, allowed))
        self.assertFalse(is_authorized(None, allowed))
