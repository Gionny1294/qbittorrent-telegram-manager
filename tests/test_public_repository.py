import re
import unittest
from pathlib import Path


class PublicRepositoryTests(unittest.TestCase):
    def test_examples_have_no_personal_home_paths(self):
        root = Path(__file__).resolve().parents[1]
        public_files = [
            root / ".env.example",
            root / "docker-compose.yml",
            root / "README.md",
            root / "README.it.md",
        ]
        for path in public_files:
            self.assertNotRegex(path.read_text(), re.compile(r"/home/[A-Za-z0-9._-]+"), path.name)

    def test_example_contains_no_token_shaped_value(self):
        example = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
        self.assertNotRegex(example, re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"))
