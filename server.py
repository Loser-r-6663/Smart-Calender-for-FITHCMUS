import os
import asyncio
from apify import Actor

from Database.Repository.user_repository import UserRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository

from DataProcessor.Standardization.User import User
from DataProcessor.TaskCreator import TaskCreator
from DataProcessor.Validator import Validator
from DataProcessor.utils.apify_storage import *

APP_ROLE = os.environ.get("APP_ROLE")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
user_repo = UserRepository(supabase_key=SUPABASE_SECRET_KEY)


async def process_public_tasks():
    await asyncio.to_thread(run_pipeline, user=None)

async def process_personal_tasks():
    users = await asyncio.to_thread(user_repo.get_all_users)
    for user in users:
        if APP_ROLE != "SERVER" or user.portal_status or user.moodle_status:
            await asyncio.to_thread(run_pipeline, user=user)

def run_pipeline(user: User | None = None):
    if user:
        repo = UserTaskRepository(user_id=user.id, supabase_key=SUPABASE_SECRET_KEY)
    else:
        repo = TaskRepository(supabase_key=SUPABASE_SECRET_KEY)
    validator = Validator()

    extracted_tasks = TaskCreator(user).create_task()
    retained_tasks = repo.get_tasks()
    tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)

    if (expired_tasks := validator.filter_expired_tasks(tasks)):
        repo.delete_tasks(expired_tasks)
        Actor.log.info(f"Deleted {len(expired_tasks)} expired tasks.")

    if (new_tasks := [task for task in tasks if not (task in retained_tasks + expired_tasks)]):
        repo.save_tasks(new_tasks)
        Actor.log.info(f"Saved {len(new_tasks)} new tasks.")

    if user: user_repo.update_user(user)

async def main(mode = "all"):  # NOTE: mode = "public" | "personal" | "all"
    if os.environ.get("APP_ROLE") == "SERVER":
        async with Actor:
            set_main_loop(asyncio.get_running_loop())
            actor_input: dict = await Actor.get_input() or {}
            mode = actor_input.get("mode", mode)

            if mode in ("public", "all"):
                Actor.log.info("Crawling public sources...")
                await process_public_tasks()

            if mode in ("personal", "all"):
                Actor.log.info("Crawling personal user sources...")
                await process_personal_tasks()
    else:
        if mode in ("public", "all"):
            await process_public_tasks()
        if mode in ("personal", "all"):
            await process_personal_tasks()

if __name__ == "__main__":
    asyncio.run(main(mode="public"))
