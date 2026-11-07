"""Reviewed Database source guards and shared test/sample utilities."""
import hashlib

from search_sample.support import (FIXTURES, TIME_FIELDS, TestTarget, adapt_request, adapt_task, read_fixture,
                                   read_target as read_test_target, validate_live_target)

DATABASE_REVISION = "7aa63cfc5453a70a12b73b099c4f56e1dc583825"
REVIEWED_FILES = {
    "Db_query.sql": "81f85d88e73500b8aac1de7002c855602e4597c5bea93af9ad9ae5463174e553",
    "DatabaseManager.py": "c4d4a14d63af61e53ec5bff8effaba801e6380db39632f22bdb0ffc83455033f",
    "tasks.py": "7c822ff9fe42928980ff7cdcca2f9ca0005719584f6fc8ed1da674d5624d6559",
}

def reviewed_schema(database_directory):
    """Refuse SQL/source drift before a schema script or supported write can run."""
    for name, expected in REVIEWED_FILES.items():
        source = (database_directory / name).read_text(encoding="utf-8")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected:
            raise RuntimeError(f"Review Database/{name} before updating the integration source fingerprint")
    return (database_directory / "Db_query.sql").read_text(encoding="utf-8")
