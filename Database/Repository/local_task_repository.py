import hashlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from DataProcessor.Standardization.ExtractedTask import ExtractedTask
from DataProcessor.Standardization.Task import ScheduledOccurrence, Task


class LocalTaskRepository:
    """An owner store with independent source facts and scheduler state."""

    ROOT = Path(__file__).resolve().parents[2]
    SCHEDULE_FIELDS = ("start_time", "end_time", "status", "recurrence", "compulsory", "flexible",
                       "scheduled_occurrences")
    JSON_COLUMNS = ("target_audience", "location", "start_time", "end_time")

    @classmethod
    def path_for_owner(cls, user_id, database_dir=None):
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("An authenticated owner is required")
        root = Path(database_dir or os.getenv("LOCAL_TASK_DB_DIR", "Database/data"))
        if not root.is_absolute():
            root = cls.ROOT / root
        return root.resolve() / (hashlib.sha256(user_id.encode()).hexdigest() + ".sqlite3")

    def __init__(self, user_id: str, database_dir=None):
        self.owner_id = user_id
        self.database_path = self.path_for_owner(user_id, database_dir)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA synchronous=FULL")
            self._migrate()
        except BaseException:
            self.connection.close()
            raise

    def _create_tasks(self):
        self.connection.execute("""CREATE TABLE tasks (
            scope TEXT NOT NULL CHECK(scope IN ('public','personal','unknown')),
            id TEXT NOT NULL, owner_id TEXT NOT NULL,
            source_payload TEXT, schedule_payload TEXT, legacy_row TEXT,
            PRIMARY KEY(scope, id))""")

    def _migrate(self):
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("CREATE TABLE IF NOT EXISTS store_owner (owner_id TEXT NOT NULL)")
            owner = self.connection.execute("SELECT owner_id FROM store_owner").fetchone()
            if owner is not None and owner[0] != self.owner_id:
                raise ValueError("SQLite store belongs to another owner")
            if owner is None:
                self.connection.execute("INSERT INTO store_owner VALUES (?)", (self.owner_id,))
            columns = {row['name'] for row in self.connection.execute("PRAGMA table_info(tasks)")}
            if not columns:
                self._create_tasks()
            elif 'source_payload' not in columns:
                self.connection.execute("ALTER TABLE tasks RENAME TO tasks_legacy")
                self._create_tasks()
                for row in self.connection.execute("SELECT * FROM tasks_legacy").fetchall():
                    raw = dict(row)
                    data = json.loads(raw.get('payload') or '{}')
                    data.update({key: value for key, value in raw.items() if value is not None and key != 'payload'})
                    for field in self.JSON_COLUMNS:
                        if isinstance(data.get(field), str):
                            data[field] = json.loads(data[field])
                    data.update(scope='unknown', owner_id=self.owner_id)
                    task_id = data.get('id')
                    if not task_id:
                        task_id = str(uuid5(NAMESPACE_URL, json.dumps(raw, sort_keys=True)))
                        data['id'] = task_id
                    self.connection.execute("INSERT INTO tasks VALUES ('unknown', ?, ?, NULL, ?, ?)",
                                            (task_id, self.owner_id, json.dumps(data), json.dumps(raw)))
                self.connection.execute("DROP TABLE tasks_legacy")

    def ingest_sources(self, groups):
        prepared = []
        for scope, tasks in groups:
            if scope not in ('public', 'personal'):
                raise ValueError("Source scope must be public or personal")
            for source in tasks:
                task = Task.from_extracted_task(source, owner_id=self.owner_id, scope=scope)
                if scope == 'personal':
                    source = source.model_copy(update={'user_id': self.owner_id})
                prepared.append((scope, task.id, self.owner_id, source.model_dump_json()))
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            for scope, task_id, owner, payload in prepared:
                previous = self.connection.execute("SELECT schedule_payload FROM tasks WHERE scope=? AND id=?",
                                                   (scope, task_id)).fetchone()
                schedule = None
                if previous is not None and previous[0] is not None:
                    saved = json.loads(previous[0])
                    refreshed = Task.from_extracted_task(ExtractedTask.model_validate_json(payload),
                                                        owner_id=owner, scope=scope).model_dump(mode='json')
                    refreshed.update(self._schedule_values(saved))
                    schedule = json.dumps(refreshed)
                self.connection.execute("""INSERT INTO tasks(scope,id,owner_id,source_payload,schedule_payload)
                    VALUES (?,?,?,?,?) ON CONFLICT(scope,id) DO UPDATE SET
                    source_payload=excluded.source_payload, schedule_payload=excluded.schedule_payload""",
                                        (scope, task_id, owner, payload, schedule))
        return {task_id for scope, task_id, _, _ in prepared if scope == 'personal'}

    def _schedule_values(self, saved):
        fields = self.SCHEDULE_FIELDS if saved.get('status') == 'scheduled' or saved.get('scheduled_occurrences') else (
            'status', 'compulsory', 'flexible')
        return {key: saved[key] for key in fields if key in saved}

    def _rows(self, *, verified=False, limit=None):
        query = "SELECT * FROM tasks WHERE owner_id=?"
        if verified:
            query += " AND scope IN ('public','personal') AND source_payload IS NOT NULL"
        query += " ORDER BY CASE scope WHEN 'public' THEN 0 WHEN 'personal' THEN 1 ELSE 2 END,id"
        params = [self.owner_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return self.connection.execute(query, params).fetchall()

    def _task(self, row):
        saved = json.loads(row['schedule_payload']) if row['schedule_payload'] else None
        if row['source_payload']:
            source = ExtractedTask.model_validate_json(row['source_payload'])
            data = saved if saved is not None else Task.from_extracted_task(
                source, owner_id=self.owner_id, scope=row['scope']).model_dump()
        else:
            data = saved
        data.update(id=row['id'], scope=row['scope'], owner_id=self.owner_id)
        return Task.model_validate(data)

    def get_tasks(self, limit=None):
        return [self._task(row) for row in self._rows(limit=limit)]

    def get_verified_tasks(self):
        return [(row['scope'], ExtractedTask.model_validate_json(row['source_payload']), self._task(row))
                for row in self._rows(verified=True)]

    def get_task(self, key):
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("Task lookup requires a scoped key")
        row = self.connection.execute("SELECT * FROM tasks WHERE scope=? AND id=? AND owner_id=?",
                                      (*key, self.owner_id)).fetchone()
        return self._task(row) if row is not None else None

    def _save(self, tasks):
        prepared = []
        for task in tasks:
            if not isinstance(task, Task) or task.owner_id not in (None, self.owner_id):
                raise ValueError("Task must belong to this owner")
            task = task.model_copy(deep=True)
            task.owner_id = self.owner_id
            if task.id is None:
                if task.scope != 'unknown':
                    raise ValueError("Verified task UUID cannot be generated locally")
                task.id = str(uuid5(NAMESPACE_URL, f"{task.source_url}|{task.title}"))
            row = self.connection.execute("SELECT source_payload FROM tasks WHERE scope=? AND id=?",
                                          task.key).fetchone()
            if task.scope != 'unknown':
                if row is None or row[0] is None:
                    raise ValueError("Verified source facts must be ingested before schedule updates")
                latest = Task.from_extracted_task(ExtractedTask.model_validate_json(row[0]),
                                                  owner_id=self.owner_id, scope=task.scope).model_dump()
                values = task.model_dump()
                latest.update(self._schedule_values(values))
                task = Task.model_validate(latest)
            prepared.append(task)
        self.connection.executemany("""INSERT INTO tasks(scope,id,owner_id,schedule_payload)
            VALUES(?,?,?,?) ON CONFLICT(scope,id) DO UPDATE SET schedule_payload=excluded.schedule_payload""",
                                    [(t.scope, t.id, self.owner_id, t.model_dump_json()) for t in prepared])
        return prepared

    def save_tasks(self, tasks):
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            return self._save(tasks)

    def save_schedule(self, tasks, scheduled):
        by_key = {task.key: task.model_copy(deep=True) for task in tasks}
        for occurrence in scheduled:
            current = by_key.setdefault(occurrence.key, occurrence.model_copy(deep=True))
            if occurrence.start_time is not None and occurrence.end_time is not None:
                saved = ScheduledOccurrence(start_time=occurrence.start_time, end_time=occurrence.end_time)
                if saved.model_dump() not in [value.model_dump() for value in current.scheduled_occurrences]:
                    current.scheduled_occurrences.append(saved)
        self.save_tasks(list(by_key.values()))

    def update_task(self, key, data):
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("Task updates require a scoped key")
        current = self.get_task(key)
        if current is None:
            raise KeyError(key)
        values = data.model_dump() if isinstance(data, Task) else dict(data)
        updated = Task.model_validate(current.model_dump() | values | {'scope': key[0], 'id': key[1], 'owner_id': self.owner_id})
        return self.save_tasks([updated])[0]

    def delete_tasks(self, tasks):
        keys = []
        for task in tasks:
            if not isinstance(task, Task) or task.owner_id not in (None, self.owner_id):
                raise ValueError("Task must belong to this owner")
            keys.append((*task.key, self.owner_id))
        with self.connection:
            self.connection.executemany("DELETE FROM tasks WHERE scope=? AND id=? AND owner_id=?", keys)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
