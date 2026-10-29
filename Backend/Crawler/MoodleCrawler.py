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
        page.goto(self.home_url)
        
        # Crawling the assignment list
        container = page.locator('//div[@data-region="event-list-container"]')
        container.scroll_into_view_if_needed()
        
        ASSIGNMENT_SELECTOR = '//div[@data-region="event-list-container"]//a'
        page.locator(ASSIGNMENT_SELECTOR).is_visible(timeout=10000)
        assignments = page.locator(ASSIGNMENT_SELECTOR).all()
        return assignments
