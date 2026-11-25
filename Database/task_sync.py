"""Shared source ingestion for authenticated UI and scheduler sessions."""

import os

from Database.Repository.local_task_repository import LocalTaskRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository


def sync_owner_tasks(owner_id, access_token, *, consume=False, limit=1000, database_dir=None):
    if not isinstance(owner_id, str) or not owner_id.strip() or not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("Both an authenticated owner and session token are required")
    public_key = os.getenv("SUPABASE_PUBLIC_KEY")
    public = TaskRepository(supabase_key=public_key).get_tasks(limit=limit)
    personal_repo = UserTaskRepository(supabase_key=public_key, access_token=access_token, user_id=owner_id)
    with LocalTaskRepository(owner_id, database_dir) as store:
        def persist(personal):
            return store.ingest_sources((("public", public), ("personal", personal)))

        if consume:
            personal_repo.pop_tasks(persist=persist, limit=limit)
        else:
            persist(personal_repo.get_tasks(limit=limit))
