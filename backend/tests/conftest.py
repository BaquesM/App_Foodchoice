"""Test setup: use an isolated temporary SQLite database, built through the Alembic migrations."""
import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="foodchoice_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"

from backend.app.db.init_db import init_db  # noqa: E402

init_db(reset=True)
