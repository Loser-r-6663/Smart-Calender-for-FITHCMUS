import pytest


@pytest.fixture(autouse=True)
def isolated_owner_store(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_TASK_DB_DIR", str(tmp_path / "owner-stores"))


@pytest.fixture(autouse=True)
def offline_requests(monkeypatch):
    from requests import ConnectionError

    def blocked(*args, **kwargs):
        raise ConnectionError("Unmocked HTTP is disabled in the offline test suite")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
