import json
import traceback

from DataProcessor.Standardization.User import User
from DataProcessor.Standardization.Task import Task

from DataProcessor.Crawler.PortalCrawler import PortalCrawler
from DataProcessor.Crawler.MoodleCrawler import MoodleCrawler

from DataProcessor.Validator import Validator

from Database.auth import sign_in, sign_up
from Database.Repository.user_repository import UserRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository
from Database.Repository.user_task_state_repository import UserTaskStateRepository

from Scheduler.scheduler import BranchAndBoundScheduler


class UserManager:
    def __init__(self):
        self.user: User
        self.access_token: str
        self.user_repo: UserRepository
        self.get_user()
    
    def update_portal_account(self):
        """Update the user's portal account information if it's missing."""
        if not (self.user.portal_username and self.user.portal_password):
            self.user.portal_username = input("Portal username: ")
            self.user.portal_password = input("Portal password: ")
            self.user_repo.update_user(self.user)

    def update_local_session(self):
        """Authenticate personal crawlers and persist their login sessions."""
        if not self.user.portal_status and self.user.portal_username and self.user.portal_password:
            try:
                portal = PortalCrawler(self.user)
                with portal.load_engine() as crawler:
                    portal.crawler = crawler
                    portal.authenticate()
                
                self.user.portal_status = True
                if portal.state:
                    self.user.portal_session = json.dumps(portal.state)
            except Exception:
                self.user.portal_status = False
                print(f"Portal login failed:")
                traceback.print_exc()

        if not self.user.moodle_status:
            try:
                moodle = MoodleCrawler(self.user)
                with moodle.load_engine() as crawler:
                    moodle.crawler = crawler
                    moodle.authenticate()
                    
                self.user.moodle_status = True
                if moodle.state:
                    self.user.moodle_session = json.dumps(moodle.state)
            except Exception:
                self.user.moodle_status = False
                print(f"Moodle login failed:")
                traceback.print_exc()

        self.user_repo.update_user(self.user)

    def get_user(self):
        username = input("Username: ") # NOTE: your_email@gmail.com
        password = input("Password: ") # NOTE: at least 6 characters
        
        try:
            self.access_token, self.user = sign_up(username, password)
        except:
            self.access_token, self.user = sign_in(username, password)
        
        self.user_repo = UserRepository(access_token=self.access_token)
        self.update_portal_account()
        self.update_local_session()

    def get_tasks(self):
        database = TaskRepository()
        public_tasks = database.get_tasks()

        database = UserTaskRepository(access_token=self.access_token, user_id=self.user.id)
        personal_tasks = database.get_tasks()

        # Combine public and personal tasks, and retrieve their states from the database
        extracted_tasks = public_tasks + personal_tasks
        state_repository = UserTaskStateRepository(access_token=self.access_token, user_id=self.user.id)
        task_states = state_repository.get_task_states(extracted_tasks)

        # Create Task objects from extracted tasks and update their states if available
        tasks: list[Task] = []
        for extracted_task in extracted_tasks:
            task = Task.from_extracted_task(extracted_task)
            if task.id in task_states:
                task = Task.model_validate({**task.model_dump(), **task_states[task.id]})
            tasks.append(task)

        expired_tasks = Validator().filter_expired_tasks(tasks)
        tasks = [task for task in tasks if task not in expired_tasks]
        return tasks

    def schedule_tasks(self, tasks: list[Task]):
        """Schedule tasks using the Branch and Bound algorithm."""
        database = UserTaskStateRepository(access_token=self.access_token, user_id=self.user.id)
        
        scheduler = BranchAndBoundScheduler(database)
        result = scheduler.schedule(tasks, initial_drl=self.user.training_points)
        result.print_timetable()
        return result


if __name__ == "__main__":
    user_manager = UserManager()
    tasks = user_manager.get_tasks()
    user_manager.schedule_tasks(tasks)
