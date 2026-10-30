"""Run with: python -X utf8 -m academic_search.demo"""
import json
from contextlib import closing
from pathlib import Path

from .fixture_adapter import create_demo_database
from .service import SearchService

CLOCK = "2026-10-30T12:00:00+07:00"
WEEK = ["2026-10-26T00:00:00+07:00", "2026-11-02T00:00:00+07:00"]
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]


def main():
    path = Path(__file__).resolve().parents[1] / "fixtures" / "search" / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    with closing(create_demo_database(tasks)) as connection:
        service = SearchService(connection)
        task = service.get_task_by_id("asg-csc10004-lab")
        print("Exact ID:", task["id"], task["title"])
        examples = [
            ("Course/type/status", {"course_code": "CSC10004", "types": ["assignment"], "statuses": ["active"]}),
            ("Due this fixed week", {"deadline_within": WEEK}),
            ("Registration open at fixed clock", {"registration_open_at": CLOCK}),
            ("Events overlapping fixed day", {"types": ["event"], "event_overlaps": DAY}),
            ("Updated in fixed period, CSC10004", {"course_code": "CSC10004", "updated_at_within": ["2026-10-20T00:00:00+07:00", "2026-10-21T00:00:00+07:00"]}),
            ("No matches", {"course_code": "CSC99999"}),
        ]
        for label, filters in examples:
            results = service.search_tasks({"filters": filters, "limit": 100})
            print(f"{label}: {json.dumps([task['id'] for task in results])}")


if __name__ == "__main__":
    main()
