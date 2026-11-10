"""Point all storage at a throwaway folder before any hookscope module is imported."""

import os
import tempfile

os.environ["HOOKSCOPE_DATA"] = tempfile.mkdtemp(prefix="hookscope-test-")

import pytest  # noqa: E402

from hookscope import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    from hookscope import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ANALYSES_DIR", tmp_path / "a")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "hookscope.db")
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    db.reset_for_tests()
    yield
    db.reset_for_tests()
