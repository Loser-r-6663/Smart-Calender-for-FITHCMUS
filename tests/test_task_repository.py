from Database.Repository.task_repository import TaskRepository


class FakeResponse:
    ok = True

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def json(self) -> list[dict]:
        return self._rows


def test_get_tasks_paginates_beyond_one_database_page(monkeypatch) -> None:
    offsets = []

    def get(url, *, params, headers, timeout):
        offsets.append(params["offset"])
        if params["offset"] == 0:
            return FakeResponse([{"id": str(index)} for index in range(1000)])
        return FakeResponse([{"id": "1000"}])

    monkeypatch.setattr("Database.Repository.task_repository.requests.get", get)
    repository = TaskRepository(
        supabase_url="https://example.test",
        supabase_key="public-key",
    )
    repository.row_to_task = lambda row: row

    tasks = repository.get_tasks(limit=None)

    assert len(tasks) == 1001
    assert offsets == [0, 1000]
