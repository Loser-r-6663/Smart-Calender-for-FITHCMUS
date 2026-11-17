"""Source and import guards for the current transaction-based Database contract."""
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path

DATABASE_DIRECTORY = Path(__file__).resolve().parents[1] / "Database"
REVIEWED_REVISION = "09681446ea856efcd709aeec88101f9cac2b4f50"
REVIEWED_SOURCES = {
    "Db_query.sql": "998f8d33c6166ec3ba16ca811e36e155e601ea2241be8be1b10014f991bc0950",
    "database_manager.py": "73589cdeea19855f81a62f678d6bc7fbf256a5e531fce53818e5ddcda5f87465",
    "db_connection.py": "0a36f2d13eaea5dc6e806a96dfb65e11cfd356cda7998b54d3a3fbf93f958a4c",
    "enums.py": "cab89798aedf133cdb9af422f8ef71e77d7ff9de32a9a90349363ca3b67d0e22",
    "task_config.py": "d40378c6bf123b19562f1e0238188f69e7f192a28a3a67b987f0e8f3459d6baf",
    "task_objects.py": "151ef95a7d18ef07b6d1bc2d9d471c694b95ce393bcfae8674b00c46e8406884",
    "task_validation.py": "87666339bca1bd7bedbd86c3d4874b08c301faf5f4ad98fc87f18e2e8d5870d6",
    "tasks.py": "b33cdadd0f613c0f3ac90d18023929db9647ba0f938c55f2fd57edb65fa35143",
    "user_objects.py": "527d423dd8e2491199611b77e5b258de2ba5277fd6fe5c5fb5b4756f37a2ccfb",
    "user_tasks.py": "4d8861e02c1fc221f908a68f726eb9c611213aa0824b6d629573c58de4854a0f",
    "user_validation.py": "b54653e80c033384e63f63f10a6459cbaa8f692c99edbaf753fa23ae9a740b3e",
    "users.py": "14e2ccc4636a1843289fe4d7f689aaa9c06e18216ca0c5faae4a0258930b2a18",
}


def reviewed_transactional_schema():
    """Check normalized sources and import locations before any database access."""
    checked = {}
    for name, expected in REVIEWED_SOURCES.items():
        path = DATABASE_DIRECTORY / name
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise RuntimeError(f"Cannot read transactional profile source Database/{name}") from None
        if sha256(source.encode("utf-8")).hexdigest() != expected:
            raise RuntimeError(f"Transactional profile source mismatch: Database/{name}")
        checked[name] = source

    package = find_spec("Database")
    locations = getattr(package, "submodule_search_locations", None) or ()
    if {Path(location).resolve() for location in locations} != {DATABASE_DIRECTORY}:
        raise RuntimeError("Transactional profile requires the Database package from this checkout")
    for name in checked:
        if name.endswith(".py"):
            spec = find_spec(f"Database.{Path(name).stem}")
            origin = getattr(spec, "origin", None)
            if not origin or Path(origin).resolve() != DATABASE_DIRECTORY / name:
                raise RuntimeError(f"Unexpected transactional profile import: Database/{name}")
    return checked["Db_query.sql"]
