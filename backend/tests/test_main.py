"""Boot-time validation (app/main.py): a malformed FERNET_KEY must fail
at boot, not on the first real encrypt/decrypt call. A subprocess is used
rather than importlib.reload -- app.main is almost certainly already
imported (with real side effects, e.g. router registration) by the time
this test runs, so a fresh process is the only reliable way to observe
its module-level boot checks actually running."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_a_malformed_fernet_key_fails_at_boot():
    env = {**os.environ, "FERNET_KEY": "not-a-real-key"}
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env, capture_output=True, text=True, cwd=str(BACKEND_DIR),
    )
    assert result.returncode != 0
    assert "FERNET_KEY is not a valid Fernet key" in result.stderr
