import json
import sys
import traceback

from DataProcessor.Standardization.User import User
from DataProcessor.Crawler.PortalCrawler import PortalCrawler
from DataProcessor.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Scheduling.service import SchedulingService

from Database.auth import sign_in, sign_up
from Database.Repository.user_repository import UserRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_preference_repository import UserTaskPreferenceRepository
from Database.Repository.user_task_repository import UserTaskRepository

from DataProcessor.Validator import Validator


def update_portal_account(access_token, user: User):
    """Update the user's portal account information if it's missing."""
    if not (user.portal_username and user.portal_password):
        user.portal_username = input("Portal username: ")
        user.portal_password = input("Portal password: ")
        UserRepository(access_token=access_token).update_user(user)

def update_local_session(access_token, user: User):
    """Authenticate personal crawlers and persist their login sessions."""
    if not user.portal_status and user.portal_username and user.portal_password:
        try:
            portal = PortalCrawler(user)
            with portal.load_engine() as crawler:
                portal.crawler = crawler
                portal.authenticate()
            
            user.portal_status = True
            if portal.state:
                user.portal_session = json.dumps(portal.state)
        except Exception:
            user.portal_status = False
            print(f"Portal login failed:")
            traceback.print_exc()

    if not user.moodle_status:
        try:
            moodle = MoodleCrawler(user)
            with moodle.load_engine() as crawler:
                moodle.crawler = crawler
                moodle.authenticate()
                
            user.moodle_status = True
            if moodle.state:
                user.moodle_session = json.dumps(moodle.state)
        except Exception:
            user.moodle_status = False
            print(f"Moodle login failed:")
            traceback.print_exc()

    UserRepository(access_token=access_token).update_user(user)

def get_tasks(interactive_adjust: bool = True):
    username = input("Username: ") # NOTE: your_email@gmail.com
    password = input("Password: ") # NOTE: at least 6 characters
    
    try:
        access_token, user = sign_up(username, password)
    except:
        access_token, user = sign_in(username, password)
    
    update_portal_account(access_token, user)
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

    user_prefs = {}
    try:
        user_prefs = UserTaskPreferenceRepository(
            access_token=access_token, user_id=user.id
        ).get_preferences()
    except Exception:
        user_prefs = {}

    scheduling_service = SchedulingService()
    schedule_run = scheduling_service.run_for_tasks(
        tasks,
        user_id=user.id,
        initial_drl=user.drl_scores,
        restrict_to_window=True,
        user_task_prefs=user_prefs,
    )
    schedule_run.schedule.print_summary()
    try:
        UserTaskPreferenceRepository(
            access_token=access_token, user_id=user.id
        ).save_schedule_outcome(
            schedule_run.schedule.selected_events,
            user_id=user.id,
            existing_prefs=user_prefs,
        )
    except Exception:
        pass
    if interactive_adjust and sys.stdin.isatty():
        schedule_run = scheduling_service.interactive_adjust_schedule(
            tasks,
            schedule_run,
            user_id=user.id,
            access_token=access_token,
            persist_to_db=True,
            initial_user_prefs=user_prefs,
            initial_drl=user.drl_scores,
            restrict_to_window=True,
        )
    return schedule_run


if __name__ == "__main__":
    get_tasks()
