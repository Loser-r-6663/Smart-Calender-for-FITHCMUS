import logging
from datetime import date
from typing import Any

import psycopg2
from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query
from starlette.requests import Request
from starlette.responses import JSONResponse

from Backend.Scheduling.service import SchedulingService, UserNotFoundError
from Database.api_authorization import require_permission
from Database.api_schemas import (
    CompletionUpdate,
    DailyTaskUpdate,
    SchedulePersistenceResponse,
    ScheduleRunRequest,
    ScheduleRunResponse,
    ScheduledEventResponse,
    TaskUpdate,
    UserDRLScoresSet,
    UserDRLScoresUpdate,
    UserUpdate,
)
from Database.database_manager import DatabaseManager
from Database.daily_task_objects import DailyTaskObject
from Database.enums import TaskStatus, TaskType
from Database.task_objects import TaskObject
from Database.user_objects import (
    UserDRLScoresObject,
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


def get_scheduling_service(
    database: DatabaseManager = Depends(get_database_manager),
) -> SchedulingService:
    return SchedulingService(database=database)


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
    "/users/{user_id}/drl",
    dependencies=[Depends(require_permission("users:read"))],
)
def get_user_drl(
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> UserDRLScoresObject:
    scores = database.get_user_drl_scores(user_id)
    if scores is None:
        raise HTTPException(status_code=404, detail="User not found")
    return scores


@app.put(
    "/users/{user_id}/drl",
    dependencies=[Depends(require_permission("users:update"))],
)
def set_user_drl(
    scores: UserDRLScoresSet,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> UserDRLScoresObject:
    saved = database.set_user_drl_scores(
        user_id, scores.model_dump(), replace=True
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="User not found")
    return saved


@app.patch(
    "/users/{user_id}/drl",
    dependencies=[Depends(require_permission("users:update"))],
)
def update_user_drl(
    updates: UserDRLScoresUpdate,
    user_id: int = Path(ge=1),
    database: DatabaseManager = Depends(get_database_manager),
) -> UserDRLScoresObject:
    saved = database.set_user_drl_scores(
        user_id, updates.model_dump(exclude_unset=True), replace=False
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="User not found")
    return saved


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


@app.post(
    "/users/{user_id}/schedule",
    response_model=ScheduleRunResponse,
    dependencies=[Depends(require_permission("daily_tasks:create"))],
)
def run_user_schedule(
    user_id: int = Path(ge=1),
    request: ScheduleRunRequest = Body(default_factory=ScheduleRunRequest),
    service: SchedulingService = Depends(get_scheduling_service),
) -> ScheduleRunResponse:
    try:
        run_result = service.run(
            user_id=user_id,
            initial_drl=request.initial_drl,
            week_start=request.week_start,
            week_end=request.week_end,
            restrict_to_window=request.restrict_to_window,
            include_unassigned_zero_point_events=request.include_unassigned_zero_point_events,
            persist=request.persist,
        )
    except UserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None

    schedule = run_result.schedule
    persistence = (
        SchedulePersistenceResponse(
            user_id=run_result.persistence.user_id,
            assigned_task_ids=list(run_result.persistence.assigned_task_ids),
            newly_assigned_count=run_result.persistence.newly_assigned_count,
            daily_task_records=list(run_result.persistence.daily_task_records),
        )
        if run_result.persistence is not None
        else None
    )
    return ScheduleRunResponse(
        status=schedule.status,
        week_start=run_result.week_start,
        week_end=run_result.week_end,
        total_tasks_loaded=run_result.total_tasks_loaded,
        prepared_tasks_count=run_result.prepared_tasks_count,
        total_drl_gained=schedule.total_drl_gained,
        raw_total_drl=schedule.raw_total_drl,
        final_total_drl=schedule.final_total_drl,
        initial_drl=schedule.initial_drl,
        final_drl=schedule.final_drl,
        selected_events=[
            ScheduledEventResponse(
                task_id=event.task_id,
                title=event.title,
                start_time=event.start_time,
                end_time=event.end_time,
                location=event.location,
                training_points=event.training_points,
                drl_category=event.drl_category,
                points_gained=event.points_gained,
            )
            for event in schedule.selected_events
        ],
        persistence=persistence,
    )
