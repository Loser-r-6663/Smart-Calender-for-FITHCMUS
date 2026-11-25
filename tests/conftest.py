import pytest


@pytest.fixture(autouse=True)
def isolated_owner_store(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_TASK_DB_DIR", str(tmp_path / "owner-stores"))
