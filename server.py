import os

from Backend.Regulation.User import User
from Backend.TaskCreator import TaskCreator
from Backend.Validator import Validator
from Database.Database import Database

os.environ["APP_ROLE"] = "SERVER"


def task_creator(user: User | None = None):
    extracted_tasks = TaskCreator(user).create_task()
    
    database = Database()
    retained_tasks = database.get_tasks()
    
    validator = Validator()
    tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)
    
    new_tasks = [task for task in tasks if task not in retained_tasks]
    database.save_tasks(new_tasks)
    
    expired_tasks = validator.filter_expired_tasks(tasks)
    database.delete_tasks(expired_tasks)
    
    return tasks


if __name__ == "__main__":
    task_creator()
    
    database = Database()
    for user in database.get_users():
        if user.portal_status or user.moodle_status:
            task_creator(user)
