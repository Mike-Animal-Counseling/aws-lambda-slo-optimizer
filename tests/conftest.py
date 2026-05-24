"""Pytest configuration for stable local test isolation."""

import os
import tempfile
from pathlib import Path

_REPO_TEMP_DIR = Path(__file__).resolve().parent.parent / ".pytest-tmp-root"
_REPO_TEMP_DIR.mkdir(exist_ok=True)

os.environ.setdefault("TMP", str(_REPO_TEMP_DIR))
os.environ.setdefault("TEMP", str(_REPO_TEMP_DIR))
os.environ.setdefault("TMPDIR", str(_REPO_TEMP_DIR))

# Reset cached tempfile resolution so pytest tmp_path uses the repo-local temp root.
tempfile.tempdir = None
