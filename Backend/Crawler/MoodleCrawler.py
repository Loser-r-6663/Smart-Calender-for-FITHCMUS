from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler


class MoodleCrawler(PlaywrightCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/MoodleHistory.txt"
        self.state_file = "Backend/Crawler/State/MoodleState.json"
        self.login_url = "https://courses.ctda.hcmus.edu.vn/login/index.php"
        self.home_url = "https://courses.ctda.hcmus.edu.vn/my/"
    
    def check_state(self, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}
        
        settings = {"headless": True, "storage_state": self.state_file}
        try:
            self.login(settings)
            return True, settings
        except ConnectionError:
            return False, {"headless": False, "storage_state": self.state_file}
    
    def login(self, settings):
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        # If the login session has expired
        if page.url.startswith(self.login_url):
            page.locator('a.login-identityprovider-btn:first-of-type').click()
        
        if settings["headless"] and page.url.startswith("https://accounts.google.com/"):
            raise ConnectionError("Please log in to Moodle using Google account manually.")
        
        page.wait_for_url(self.home_url, timeout=0)
        page.wait_for_load_state("networkidle")
        
        context.storage_state(path=self.state_file)
        browser.close()
    
    def browse_page(self, page):
        raw_tasks: list[RawTask] = []
        due_date = ""
        
        try:
            wrapper_loc = page.locator('div[data-region="event-list-wrapper"]')
            wrapper_loc.wait_for(state="attached", timeout=5000)
            wrapper_loc.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            # Empty timeline or no assignments due on Moodle
            return []
            
        wrapper = page.locator('div[data-region="event-list-wrapper"] > div').all()
        for content in wrapper:
            try:
                if content.get_attribute('class') == "mt-3":
                    due_date = content.locator('h4').inner_text()
                    continue
                
                raw_task = RawTask()
                
                link_el = content.locator('h5.event-name > a')
                if link_el.count() == 0:
                    continue
                link = link_el.get_attribute('href')
                if link == self.last_post:
                    raw_tasks.clear()
                    continue
                
                raw_task.link = link
                raw_task.type = "assignment"
                raw_task.title = link_el.get_attribute('title')
                
                time_el = content.locator('small.text-end')
                due_time = time_el.inner_text() if time_el.count() > 0 else ""
                raw_task.deadline = f"{due_date} {due_time}".strip()
                
                course_el = content.locator('small.mb-0')
                if course_el.count() > 0:
                    course_text = course_el.inner_text()
                    if " · " in course_text:
                        parts = course_text.split(" · ")
                        raw_task.course = parts[1].split(" - ")[0].strip() if len(parts) > 1 else parts[0].strip()
                    else:
                        raw_task.course = course_text.strip()
                
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing assignment on Moodle: {e}")
        
        return raw_tasks[::-1]
