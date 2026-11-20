from Backend.Regulation.User import User

from Database.auth import sign_in, sign_up
from Database.Repository.user_repository import UserRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository

from Backend.Validator import Validator


def update_portal_account(access_token, user: User):
    """Update the user's portal account information if it's missing."""
    user.portal_username = input("Portal username: ")
    user.portal_password = input("Portal password: ")
    UserRepository(access_token=access_token).update_user(user)

def update_local_session(access_token, user):
    pass

def get_tasks():
    username = input("Username: ") # NOTE: your_email@gmail.com
    password = input("Password: ") # NOTE: at least 6 characters
    
    try:
        access_token, user = sign_up(username, password)
    except:
        access_token, user = sign_in(username, password)
    
    if not (user.portal_username and user.portal_password):
        update_portal_account(access_token, user)
    if not (user.portal_session and user.moodle_session):
        update_local_session(access_token, user)
    
    database = TaskRepository()
    public_tasks = database.get_tasks()

    database = UserTaskRepository(access_token=access_token, user_id=user.id)
    personal_tasks = database.get_tasks()
    
    tasks = public_tasks + personal_tasks
    expired_tasks = Validator().filter_expired_tasks(tasks)
    tasks = [task for task in tasks if task not in expired_tasks]
    
    # tasks = Task(tasks) NOTE: New model of regulation, not implemented yet
    # retained_tasks = SQLite.get_tasks()
    # tasks = Validator().deduplicate_task(tasks, retained_tasks)
    print(tasks)


if __name__ == "__main__":
    get_tasks()
