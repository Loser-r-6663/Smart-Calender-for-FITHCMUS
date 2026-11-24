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
from Database.Repository.local_task_repository import LocalTaskRepository

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
        personal_tasks = database.pop_tasks()

        tasks = public_tasks + personal_tasks
        expired_tasks = Validator().filter_expired_tasks(tasks)
        tasks = [task for task in tasks if task not in expired_tasks]

        with LocalTaskRepository(self.user.id) as database:
            tasks = [Task.from_extracted_task(task) for task in tasks]
            retained_tasks = database.get_tasks()
            tasks = Validator().deduplicate_task(tasks, retained_tasks)

            new_tasks = [task for task in tasks if task not in retained_tasks]
            database.save_tasks(new_tasks)

        return tasks

    def schedule_tasks(self):
        tasks = self.get_tasks()

        with LocalTaskRepository(self.user.id) as database:
            scheduler = BranchAndBoundScheduler(database)
            result = scheduler.schedule(tasks, initial_drl=self.user.training_points)
            result.print_timetable()

        self.user.training_points.update(result.final_drl)
        self.user_repo.update_user(self.user)
        return result


if __name__ == "__main__":
    UserManager().schedule_tasks()
