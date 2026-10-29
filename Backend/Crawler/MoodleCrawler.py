from Backend.Crawler.BaseCrawler import PlaywrightCrawler


class MoodleCrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/MoodleState.json"
        self.login_url = "https://courses.ctda.hcmus.edu.vn/login/index.php"
        self.home_url = "https://courses.ctda.hcmus.edu.vn/my/"
    
    def check_state(self, p, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}
        
        browser_settings = {"headless": True, "storage_state": self.state_file}
        try:
            self.login(p, browser_settings)
            return True, browser_settings
        except ConnectionError:
            return False, {"headless": False, "storage_state": self.state_file}
    
    def login(self, p, browser_settings):
        browser, context, page = self.start_browser(p, browser_settings)
        page.goto(self.home_url)
        
        # If the login session has expired
        if page.url.startswith(self.login_url):
            page.locator('a.login-identityprovider-btn:first-of-type').click()
        
        if browser_settings["headless"] and page.url.startswith("https://accounts.google.com/"):
            raise ConnectionError("Please log in to Moodle using Google account manually.")
        
        page.wait_for_url(self.home_url, timeout=0)
        page.wait_for_load_state("networkidle")
        
        context.storage_state(path=self.state_file)
        browser.close()
    
    def interact(self, page):
        page.goto(self.home_url, wait_until="networkidle")
        raw_tasks = []
        
        container = page.locator('div[data-region="event-list-container"]')
        container.scroll_into_view_if_needed()
        
        wrapper = page.locator('div[data-region="event-list-wrapper"]').all()
        for content in wrapper:
            raw_task = {"Title": "N/A", "Link": "N/A", "DueDatetime": "N/A", "Course": "N/A"}
            
            try:
                due_date = content.locator('h4').inner_text()
                
                items = content.locator('div[data-region="event-list-item"]').all()
                for item in items:
                    title = item.locator('h5.event-name > a').get_attribute('title')
                    raw_task["Title"] = title
                    
                    link = item.locator('h5.event-name > a').get_attribute('href')
                    raw_task["Link"] = link
                    
                    due_time = item.locator('small.text-end').inner_text()
                    raw_task["DueDatetime"] = f"{due_date} {due_time}"
                    
                    course = item.locator('small.mb-0').inner_text()
                    raw_task["Course"] = course                    
            except Exception as e:
                print(f"Error when parsing assignment on Moodle: {e}")
            
            raw_tasks.append(raw_task)
        return raw_tasks
