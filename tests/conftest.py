"""Keep automated tests isolated from the review dashboard database."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


TEST_DATABASE = Path(tempfile.gettempdir()) / f"safesense-pytest-{os.getpid()}.db"
os.environ["SAFESENSE_DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"


def pytest_sessionfinish(session, exitstatus):
    from safesense.database import engine

    engine.dispose()
    for suffix in ("", "-shm", "-wal"):
        (Path(f"{TEST_DATABASE}{suffix}")).unlink(missing_ok=True)
