"""Test-only PostgreSQL target guards and explicit legacy fixture adaptation."""
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/search"
DATABASE_REVISION = "7aa63cfc5453a70a12b73b099c4f56e1dc583825"
REVIEWED_FILES = {
    "Db_query.sql": "81f85d88e73500b8aac1de7002c855602e4597c5bea93af9ad9ae5463174e553",
    "DatabaseManager.py": "c4d4a14d63af61e53ec5bff8effaba801e6380db39632f22bdb0ffc83455033f",
    "tasks.py": "7c822ff9fe42928980ff7cdcca2f9ca0005719584f6fc8ed1da674d5624d6559",
}
TIME_FIELDS = ("registration_start", "registration_end", "start_time", "end_time", "deadline", "updated_at")


def read_fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def adapt_task(task):
    """Adapt only the controlled fixture vocabulary, without changing its meaning."""
    result = copy.deepcopy(task)
    course = result.pop("course_code")
    if course is not None and not re.fullmatch(r"[A-Z]{3}[0-9]{5}", course):
        raise ValueError("Unexpected fixture course code")
    result["course"] = course
    if result.pop("embedding") is not None:
        raise ValueError("Fixture embeddings are unsupported")
    recurrence = result["recurrence"]
    if recurrence in (None, "NONE"):
        result["recurrence"] = None
    elif recurrence == "WEEKLY:FRI" and result["id"] == "class-csc10004":
        result["recurrence"] = "T6 07:30-11:00"
    else:
        raise ValueError("Fixture recurrence needs an explicit mapping")
    for key in TIME_FIELDS:
        if result[key] is not None:
            value = datetime.fromisoformat(result[key].replace("Z", "+00:00"))
            if value.utcoffset() is None:
                raise ValueError("Fixture datetime must be aware")
            result[key] = value
    if type(result["training_points"]) is not int:
        raise ValueError("The current database cannot represent unknown fixture points")
    return result


def adapt_request(request):
    result = copy.deepcopy(request)
    filters = result.get("filters", {})
    if "course_code" in filters:
        value = filters["course_code"]
        if "course" in filters or not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}[0-9]{5}", value):
            raise ValueError("Unexpected fixture course filter")
        filters["course"] = filters.pop("course_code")
    return result


@dataclass(frozen=True)
class TestTarget:
    host: str
    database: str
    user: str
    password: str = field(repr=False)
    port: int

    def manager_kwargs(self):
        return {"host": self.host, "database": self.database, "user": self.user,
                "password": self.password, "port": self.port}


def read_test_target(environ):
    names = ("HOST", "NAME", "USER", "PASSWORD", "PORT", "CONFIRM")
    values = {name: environ.get(f"SEARCH_TEST_DB_{name}") for name in names}
    if any(not value for value in values.values()):
        raise RuntimeError("Explicit SEARCH_TEST_DB_HOST/NAME/USER/PASSWORD/PORT/CONFIRM settings are required")
    if not re.fullmatch(r"[a-z][a-z0-9_]*_search_test", values["NAME"]):
        raise RuntimeError("Dedicated database name must end with _search_test and use lowercase ASCII identifiers")
    if values["CONFIRM"] != values["NAME"]:
        raise RuntimeError("SEARCH_TEST_DB_CONFIRM must exactly match the dedicated database name")
    try:
        port = int(values["PORT"])
    except ValueError:
        raise RuntimeError("SEARCH_TEST_DB_PORT must be an integer") from None
    if not 1 <= port <= 65535:
        raise RuntimeError("SEARCH_TEST_DB_PORT must be between 1 and 65535")
    return TestTarget(values["HOST"], values["NAME"], values["USER"], values["PASSWORD"], port)


def validate_live_target(connection, target):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), session_user")
        identity = cursor.fetchone()
    dsn = connection.get_dsn_parameters()
    if (identity != (target.database, target.user)
            or dsn.get("host") != target.host or dsn.get("port") != str(target.port)):
        raise RuntimeError("Connected target does not match the explicit dedicated test configuration")


def reviewed_schema(database_directory):
    """Refuse SQL/source drift before a schema script or supported write can run."""
    for name, expected in REVIEWED_FILES.items():
        source = (database_directory / name).read_text(encoding="utf-8")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected:
            raise RuntimeError(f"Review Database/{name} before updating the integration source fingerprint")
    return (database_directory / "Db_query.sql").read_text(encoding="utf-8")
