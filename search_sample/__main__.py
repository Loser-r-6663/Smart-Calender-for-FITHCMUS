"""Seed, demonstrate, search and reset a dedicated local PostgreSQL sample."""
import argparse
import hashlib
import os
from pathlib import Path

from academic_search import SearchService
from academic_search.postgres import TASK_FIELDS
from academic_search.validation import SearchValidationError, validate_request

from .support import read_target, validate_live_target

SCHEMA = "search_sample"
OWNER_TAG = "smart-calendar-search-sample-v1"
SOURCE_REVISION = "7aa63cfc5453a70a12b73b099c4f56e1dc583825"
SCHEMA_HASH = "81f85d88e73500b8aac1de7002c855602e4597c5bea93af9ad9ae5463174e553"
TABLES = ("daily_tasks", "user_tasks", "tasks", "users", "_sample_meta")


def sample_target(environ):
    target = read_target(environ, prefix="SEARCH_SAMPLE_DB")
    if target.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The sample target must be an explicit local loopback host")
    return target


def schema_source():
    source = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != SCHEMA_HASH:
        raise RuntimeError("Sample SQL differs from the reviewed Database snapshot; review it before use")
    return source


def validate_transaction(connection, target):
    if connection.autocommit:
        raise RuntimeError("Sample commands require an explicit transaction, not autocommit")
    validate_live_target(connection, target)


def owned_schema(connection, target):
    """Check namespace ownership and the exact setup marker before touching data."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname = %s",
                       (SCHEMA,))
        owner = cursor.fetchone()
        if owner is None:
            return False
        if owner[0] != target.user:
            raise RuntimeError("The sample schema is owned by a different role")
        cursor.execute("SELECT to_regclass('search_sample._sample_meta')")
        if cursor.fetchone()[0] is None:
            raise RuntimeError("Refusing an existing schema without this setup's ownership marker")
        cursor.execute("SELECT owner_tag, schema_hash FROM search_sample._sample_meta")
        if cursor.fetchall() != [(OWNER_TAG, SCHEMA_HASH)]:
            raise RuntimeError("Sample ownership/source marker differs; refusing to modify it")
    return True


def seed(connection, target):
    from .data import OWNER, OTHER, CLOCK, WORK_DATE, owner_for, sample_tasks

    validate_transaction(connection, target)
    source = schema_source()
    exists = owned_schema(connection, target)
    with connection.cursor() as cursor:
        if not exists:
            cursor.execute("CREATE SCHEMA search_sample")
        cursor.execute("SET LOCAL search_path TO search_sample, pg_catalog")
        if not exists:
            cursor.execute(source)
            cursor.execute("CREATE TABLE _sample_meta (owner_tag TEXT PRIMARY KEY, schema_hash TEXT NOT NULL)")
            cursor.execute("INSERT INTO _sample_meta VALUES (%s, %s)", (OWNER_TAG, SCHEMA_HASH))
        users = {}
        for username in (OWNER, OTHER):
            email = f"{username}@fixtures.example.invalid"
            cursor.execute("INSERT INTO users (username, email) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
                           (username, email))
            cursor.execute("SELECT id, email FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
            if row is None or row[1] != email:
                raise RuntimeError("A sample username has conflicting data; use explicit reset after review")
            users[username] = row[0]
        tasks = sample_tasks()
        columns = ", ".join(TASK_FIELDS)
        placeholders = ", ".join("%s" for _ in TASK_FIELDS)
        for task in tasks:
            if set(task) != set(TASK_FIELDS):
                raise RuntimeError("Sample task fields differ from the PostgreSQL projection")
            cursor.execute(f"INSERT INTO tasks ({columns}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING",
                           tuple(task[field] for field in TASK_FIELDS))
            cursor.execute("INSERT INTO user_tasks (user_id, task_id, assigned_at) VALUES (%s, %s, %s) "
                           "ON CONFLICT (user_id, task_id) DO NOTHING", (users[owner_for(task["id"])], task["id"], CLOCK))
        for task_id in ("class-csc10004", "asg-csc10004-lab"):
            cursor.execute("INSERT INTO daily_tasks (work_date, task_id, is_completed_today) VALUES (%s, %s, %s) "
                           "ON CONFLICT (work_date, task_id) DO NOTHING", (WORK_DATE, task_id, False))
        cursor.execute("SELECT count(*) FROM tasks")
        return cursor.fetchone()[0]


def reset(connection, target):
    validate_transaction(connection, target)
    if not owned_schema(connection, target):
        return
    with connection.cursor() as cursor:
        # RESTRICT preserves external dependencies; any failure rolls back every drop.
        for table in TABLES:
            cursor.execute(f"DROP TABLE search_sample.{table} RESTRICT")
        cursor.execute("DROP SCHEMA search_sample RESTRICT")


def sample_service(connection, target):
    validate_transaction(connection, target)
    if not owned_schema(connection, target):
        raise RuntimeError("Sample is not initialized; run python -m search_sample seed explicitly")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO search_sample, pg_catalog")
        cursor.execute("SELECT id FROM users WHERE username = %s", ("sample_owner",))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Sample owner is absent; run python -m search_sample seed explicitly")
    return SearchService.from_connection(connection, user_id=row[0])


def demo(connection, target):
    from .examples import EXAMPLES

    search = sample_service(connection, target)
    task = search.get_task_by_id("asg-csc10004-lab")
    if task is None or task["id"] != "asg-csc10004-lab":
        raise RuntimeError("Exact-lookup example did not match its expected ID")
    print("Exact lookup:", task["id"], "|", task["title"])
    if search.get_task_by_id("sample-missing") is not None:
        raise RuntimeError("Missing-lookup example unexpectedly found a task")
    print("Missing lookup: None")
    for label, request, expected in EXAMPLES:
        rows = search.search_tasks(request)
        if [task["id"] for task in rows] != expected:
            raise RuntimeError(f"Demo expectation failed: {label}; seeded rows may have been edited")
        print(label, request)
        print([(task["id"], task["title"]) for task in rows])
    print("All demo expectations passed against PostgreSQL.")


def search(connection, target, request, *, interpret=False):
    service = sample_service(connection, target)
    if interpret:
        response = service.interpret_and_search(request)
        print("Remaining keyword:", response.interpretation.remaining_keyword)
        print("Effective filters:", response.interpretation.effective_filters)
        rows = response.results
    else:
        rows = service.search_tasks(request)
    if not rows:
        print("No tasks match.")
    for task in rows:
        print(task["id"], "|", task["title"])


def search_request(args):
    request = {}
    filters = {}
    if args.query is not None:
        request["keyword"] = args.query
    if args.course is not None:
        filters["course"] = args.course
    if args.type is not None:
        filters["types"] = [args.type]
    if filters:
        request["filters"] = filters
    if args.limit is not None:
        request["limit"] = args.limit
    validate_request(request)
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-reset", action="store_true", help="explicitly remove only setup-owned sample tables")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "demo", "reset"):
        command = commands.add_parser(name)
        command.add_argument("--confirm-reset", action="store_true", default=argparse.SUPPRESS,
                             help=argparse.SUPPRESS)
    search_parser = commands.add_parser("search", help="read tasks assigned to the sample owner")
    search_parser.add_argument("--query", help="literal keyword text unless --interpret is enabled")
    search_parser.add_argument("--interpret", action="store_true", help="interpret supported Vietnamese point expressions")
    search_parser.add_argument("--course", help="exact course text")
    search_parser.add_argument("--type", help="single task type")
    search_parser.add_argument("--limit", type=int, help="result limit using existing Search bounds")
    args = parser.parse_args(argv)
    if args.command == "reset" and not args.confirm_reset:
        parser.error("reset requires --confirm-reset")
    if args.command == "search":
        try:
            request = search_request(args)
        except SearchValidationError as error:
            parser.error(str(error))
    try:
        target = sample_target(os.environ)
    except RuntimeError as error:
        parser.error(str(error))
    try:
        import psycopg2
    except ImportError:
        parser.error("Install psycopg2-binary in the project environment")
    try:
        connection = psycopg2.connect(**target.manager_kwargs())
    except Exception:
        parser.error("Local sample connection failed; check dedicated settings privately")
    try:
        connection.autocommit = False
        if args.command in {"demo", "search"}:
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
            if args.command == "demo":
                demo(connection, target)
            else:
                search(connection, target, request, interpret=args.interpret)
            connection.rollback()
        elif args.command == "seed":
            count = seed(connection, target)
            connection.commit()
            print(f"Sample seeded: {count} task rows. Existing rows were preserved.")
        else:
            reset(connection, target)
            connection.commit()
            print("Owned sample objects removed. Run seed to recreate them.")
    except Exception as error:
        connection.rollback()
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else "PostgreSQL command failed"
        parser.exit(1, message + "; transaction rolled back.\n")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
