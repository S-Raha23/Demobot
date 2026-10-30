import os

os.environ["DEMOBOT_FIXTURES"] = "1"  # tests never make paid calls

from pathlib import Path

import pytest

from demobot import db
from demobot.config import settings


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own data dir and ledger; nothing touches the real ones."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    eng = db.make_engine(f"sqlite:///{tmp_path / 'ledger.db'}")
    db.init_db(eng)
    monkeypatch.setattr(db, "_engine", eng)
