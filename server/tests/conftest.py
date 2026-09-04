"""Suite-wide tests environment (loaded before ANY test module).

Pins MINTA_DATABASE_URL to a per-process temp sqlite so the engine that
`config.py` creates at import time is deterministic, no matter which test
module happens to import `config`/`main` first during collection. Without
this, test_main_search's module-level env setup raced against other test
modules (e.g. test_lifecycle_scanner imports `config.Base` at module level)
and the app could end up writing a different DB than the test queried.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="minta_testsuite_")
os.environ.setdefault(
    "MINTA_DATABASE_URL",
    f"sqlite:///{_TMP.replace(os.sep, '/')}/suite.db",
)
os.environ.setdefault("MINTA_API_KEY", "test-key")
