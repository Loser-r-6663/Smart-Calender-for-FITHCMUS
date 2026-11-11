import logging
from datetime import date
from typing import Any

import psycopg2
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from starlette.requests import Request
from starlette.responses import JSONResponse

from Database.api_authorization import require_permission
from Database.api_schemas import (
    CompletionUpdate,
    DailyTaskUpdate,
    TaskUpdate,
    UserUpdate,
)
from Database.database_manager import DatabaseManager
from Database.daily_task_objects import DailyTaskObject
from Database.enums import TaskStatus, TaskType
from Database.task_objects import TaskObject
from Database.user_objects import (
    UserObject,
    UserTaskObject,
)
from Database.task_validation import TaskData
from Database.user_validation import UserData


logger = logging.getLogger(__name__)
app = FastAPI(title="Smart Calendar Database API", version="1.0.0")
database_manager = DatabaseManager()


def get_database_manager() -> DatabaseManager:
    return database_manager


@app.exception_handler(psycopg2.IntegrityError)
async def handle_integrity_error(
    request: Request, _error: psycopg2.IntegrityError
) -> JSONResponse:
    logger.info(
        "Database constraint rejected %s %s (%s)",
        request.method,
        request.url.path,
        type(_error).__name__,
    )
    return JSONResponse(
        status_code=409, content={"detail": "Database constraint conflict"}
    )


@app.exception_handler(psycopg2.Error)
async def handle_database_error(
    request: Request, _error: psycopg2.Error
) -> JSONResponse:
    logger.exception(
        "Database request failed: %s %s (%s)",
        request.method,
        request.url.path,
        type(_error).__name__,
    )
    return JSONResponse(
        status_code=500, content={"detail": "Database operation failed"}
    )


@app.exception_handler(ValueError)
async def handle_validation_error(
    _request: Request, error: ValueError
) -> JSONResponse:
    logger.debug(
        "Request rejected by validation: %s %s",
        _request.method,
        _request.url.path,
    )
    return JSONResponse(status_code=422, content={"detail": str(error)})


@app.post(
    "/tasks",
    status_code=201,
    dependencies=[Depends(require_permission("tasks:create"))],
)
def create_task(
    task: TaskData,
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    return database.create_task(task.model_dump(exclude_unset=True))


@app.get(
    "/tasks",
    dependencies=[Depends(require_permission("tasks:read"))],
)
def list_tasks(
    status: TaskStatus | None = None,
    task_type: TaskType | None = Query(default=None, alias="type"),
    database: DatabaseManager = Depends(get_database_manager),
) -> list[TaskObject]:
    return database.list_tasks(status=status, task_type=task_type)


@app.get(
    "/tasks/{task_id}",
    dependencies=[Depends(require_permission("tasks:read"))],
)
def get_task(
    task_id: str,
    database: DatabaseManager = Depends(get_database_manager),
) -> TaskObject:
    task = database.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch(
    "/tasks/{task_id}",
    dependencies=[Depends(require_permission("tasks:update"))],
)
def update_task(
    task_id: str,
    updates: TaskUpdate,
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    task = database.update_task(task_id, updates.model_dump(exclude_unset=True))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    dependencies=[Depends(require_permission("tasks:delete"))],
)
def delete_task(
    task_id: str,
    database: DatabaseManager = Depends(get_database_manager),
) -> None:
    if not database.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@app.post(
    "/users",
    status_code=201,
    dependencies=[Depends(require_permission("users:create"))],
)
def create_user(
    user: UserData,
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    return database.create_user(user.username, user.email, user.full_name)


@app.get(
    "/users/{user_id}",
    dependencies=[Depends(require_permission("users:read"))],
)
def get_user(
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> UserObject:
    user = database.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch(
    "/users/{user_id}",
    dependencies=[Depends(require_permission("users:update"))],
)
def update_user(
    updates: UserUpdate,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    user = database.update_user(
        user_id, updates.model_dump(exclude_unset=True)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.delete(
    "/users/{user_id}",
    status_code=204,
    dependencies=[Depends(require_permission("users:delete"))],
)
def delete_user(
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> None:
    if not database.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")


@app.get(
    "/users/{user_id}/tasks",
    dependencies=[Depends(require_permission("user_tasks:read"))],
)
def get_user_tasks(
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> list[UserTaskObject]:
    return database.get_user_tasks(user_id)


@app.put(
    "/users/{user_id}/tasks/{task_id}",
    status_code=201,
    dependencies=[Depends(require_permission("user_tasks:create"))],
)
def assign_task(
    task_id: str,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    if not database.assign_task(user_id, task_id):
        raise HTTPException(status_code=409, detail="Task is already assigned")
    return {"user_id": user_id, "task_id": task_id, "assigned": True}


@app.delete(
    "/users/{user_id}/tasks/{task_id}",
    status_code=204,
    dependencies=[Depends(require_permission("user_tasks:delete"))],
)
def unassign_task(
    task_id: str,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> None:
    if not database.unassign_task(user_id, task_id):
        raise HTTPException(status_code=404, detail="Task assignment not found")


@app.get(
    "/users/{user_id}/daily-tasks",
    dependencies=[Depends(require_permission("daily_tasks:read"))],
)
def get_daily_tasks(
    work_date: date,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> list[DailyTaskObject]:
    return database.get_tasks_by_date(user_id, work_date)


@app.put(
    "/daily-tasks/{work_date}/{task_id}",
    dependencies=[Depends(require_permission("daily_tasks:create"))],
)
def set_daily_task(
    work_date: date,
    task_id: str,
    update: DailyTaskUpdate,
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    return database.set_daily_task(work_date, task_id, update.is_completed_today)


@app.patch(
    "/daily-tasks/{work_date}/{task_id}/completion",
    dependencies=[Depends(require_permission("daily_tasks:update"))],
)
def set_daily_task_completion(
    work_date: date,
    task_id: str,
    update: CompletionUpdate,
    database: DatabaseManager = Depends(get_database_manager),
) -> dict[str, Any]:
    result = database.set_daily_task_completion(work_date, task_id, update.is_completed)
    if result is None:
        raise HTTPException(status_code=404, detail="Daily task not found")
    return result


@app.delete(
    "/daily-tasks/{work_date}/{task_id}",
    status_code=204,
    dependencies=[Depends(require_permission("daily_tasks:delete"))],
)
def remove_daily_task(
    work_date: date,
    task_id: str,
    database: DatabaseManager = Depends(get_database_manager),
) -> None:
    if not database.remove_daily_task(work_date, task_id):
        raise HTTPException(status_code=404, detail="Daily task not found")
