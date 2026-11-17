# Dùng thay server.py
from apify import Actor
from Backend.Regulation.User import User
from Backend.TaskCreator import TaskCreator
from Backend.Validator import Validator
from Database.Database import Database


def run_pipeline(user: User | None = None):
    database = Database(user)
    validator = Validator()
    
    extracted_tasks = TaskCreator(user).create_task()
    retained_tasks = database.get_tasks(limit=1000)

    tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)
    new_tasks = [task for task in tasks if task.id is None]

    if new_tasks:
        database.save_tasks(new_tasks)
        Actor.log.info(f"Saved {len(new_tasks)} new tasks.")

    expired_tasks = validator.filter_expired_tasks(tasks)
    if expired_tasks:
        database.delete_tasks(expired_tasks)
        Actor.log.info(f"Deleted {len(expired_tasks)} expired tasks.")

    if user:
        database.update_user(user)

def main():
    with Actor:
        actor_input: dict = Actor.get_input() or {}
        mode = actor_input.get("mode", "all")  # NOTE: "public", "personal", or "all"

        if mode in ("public", "all"):
            Actor.log.info("Crawling public sources...")
            run_pipeline(user=None)

        if mode in ("personal", "all"):
            Actor.log.info("Crawling personal user sources...")
            for user in Database().get_users():
                if user.portal_status or user.moodle_status:
                    run_pipeline(user=user)


if __name__ == "__main__":
    main()