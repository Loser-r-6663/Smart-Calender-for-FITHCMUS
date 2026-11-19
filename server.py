import os
import asyncio
from apify import Actor

from Backend.Regulation.User import User
from Backend.TaskCreator import TaskCreator
from Backend.Validator import Validator
from Database.Database import Database
from Backend.utils.apify_storage import *


def run_pipeline(user: User | None = None):
    database = Database(user)
    validator = Validator()
    
    extracted_tasks = TaskCreator(user).create_task()
    retained_tasks = database.get_tasks()
    tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)

    if (expired_tasks := validator.filter_expired_tasks(tasks)):
        database.delete_tasks(expired_tasks)
        Actor.log.info(f"Deleted {len(expired_tasks)} expired tasks.")

    if (new_tasks := [task for task in tasks if not (task in retained_tasks + expired_tasks)]):
        database.save_tasks(new_tasks)
        Actor.log.info(f"Saved {len(new_tasks)} new tasks.")

    if user: database.update_user(user)

async def main(mode = None):
    if os.environ.get("APP_ROLE") == "SERVER":
        async with Actor:
            set_main_loop(asyncio.get_running_loop())
            actor_input: dict = await Actor.get_input() or {}
            mode = mode or actor_input.get("mode", "all")  # NOTE: "public", "personal", or "all"

            if mode in ("public", "all"):
                Actor.log.info("Crawling public sources...")
                await asyncio.to_thread(run_pipeline,user=None)

            if mode in ("personal", "all"):
                Actor.log.info("Crawling personal user sources...")
                users = await asyncio.to_thread(Database().get_users)
                for user in users:
                    if user.portal_status or user.moodle_status:
                        await asyncio.to_thread(run_pipeline,user=user)
    else:
        if mode in ("public", "all"):
            await asyncio.to_thread(run_pipeline, user=None)
        if mode in ("personal", "all"):
            users = await asyncio.to_thread(Database().get_users)
            for user in users:
                if user.portal_status or user.moodle_status:
                    await asyncio.to_thread(run_pipeline, user=user)

if __name__ == "__main__":
    asyncio.run(main(mode="all"))