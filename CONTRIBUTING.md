# Contributing

Open an issue before large changes. Never include tokens, IDs, private URLs, torrent metadata or downloaded content.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m compileall -q .
bandit -q -r . -x ./tests,./data,./logs
docker compose config --quiet
```

Use focused commits, add tests for behavior changes and update both READMEs when user-facing configuration changes. By contributing, you agree to follow the Code of Conduct and license contributions under MIT.
