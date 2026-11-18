import os
import json
from datetime import datetime

from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Regulation.User import User
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler


class MoodleCrawler(PlaywrightCrawler):
    def __init__(self, user: User):
        self.history_key = None
        self.state_key = "MoodleState"
        
        self.state: dict[str, list[dict]] = {}
        if user.moodle_session:
            self.state = json.loads(user.moodle_session)
        
        self.login_url = "https://courses.ctda.hcmus.edu.vn/login/index.php"
        self.home_url = "https://courses.ctda.hcmus.edu.vn/my/"
        self.user = user
    
    def check_state(self):
        if not self.state:
            assert os.environ.get("APP_ROLE") != "SERVER"
            return False, {"headless": False, "storage_state": None}
        
        settings = {"headless": True, "storage_state": self.state}
        try:
            self.login(settings)
            return True, settings
        except ConnectionError:
            assert os.environ.get("APP_ROLE") != "SERVER"
            return False, {"headless": False, "storage_state": self.state}
    
    def login(self, settings):
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        # If the login session has expired
        if page.url.startswith(self.login_url):
            page.locator('a.login-identityprovider-btn:first-of-type').click()
        
        if settings["headless"] and page.url.startswith("https://accounts.google.com/"):
            raise ConnectionError("Please log in to Moodle using Google account manually.")
        
        page.wait_for_url(self.home_url, timeout=0)
        page.wait_for_load_state("networkidle")
        
        if os.environ.get("APP_ROLE") == "SERVER":
            self.state.update(context.storage_state())
        else:
            state_file = f"Backend/Crawler/State/{self.state_key}.json"
            self.state.update(context.storage_state(path=state_file))
        browser.close()
    
    def browse_page(self, page):
        raw_tasks: list[RawTask] = []
        due_date = ""
        
        page.locator('div[data-region="event-list-wrapper"]').scroll_into_view_if_needed()
        wrapper = page.locator('div[data-region="event-list-wrapper"] > div').all()
        for content in wrapper:
            try:
                if content.get_attribute('class') == "mt-3":
                    due_date = content.locator('h4').inner_text()
                    continue
                
                raw_task = RawTask()
                
                link = content.locator('h5.event-name > a').get_attribute('href')
                if link == self.last_post:
                    raw_tasks.clear()
                    continue
                
                raw_task.link = link
                raw_task.type = "assignment"
                raw_task.title = content.locator('h5.event-name > a').get_attribute('title')
                
                due_time = content.locator('small.text-end').inner_text()
                raw_task.deadline = datetime.strptime(f"{due_date} {due_time}", "%A, %d %B %Y %H:%M")
                
                raw_task.course = content.locator('small.mb-0').inner_text().split(" · ")[1].split(" - ")[0]
                
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing assignment on Moodle: {e}")
        
        return raw_tasks[::-1]
