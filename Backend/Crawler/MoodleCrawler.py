from Backend.Crawler.BaseCrawler import PlaywrightCrawler
import re


HOME_URL = re.compile(r"https://courses\.ctda\.hcmus\.edu\.vn/my/?(?:[?#].*)?$")
HOME_SELECTOR = (
    "body#page-my-index, "
    "[data-region='myoverview'], "
    "[data-region='course-content'], "
    ".block_myoverview"
)
ASSIGNMENT_SELECTOR = '//div[@data-region="event-list-container"]//a'


class MoodleCrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/MoodleState.json"
        self.login_url = "https://courses.ctda.hcmus.edu.vn/my/"
        self.home_url = "https://courses.ctda.hcmus.edu.vn/my/"
    
    def login(self, p, state_file):
        if state_file["NotFound"] or state_file["AllExpires"]:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            
            page.goto(self.login_url)
            
            page.wait_for_url(HOME_URL, timeout=0)
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(HOME_SELECTOR, timeout=0)
            
            context.storage_state(path=self.state_file)
            browser.close()
    
    def interact(self, page):
        page.goto(self.home_url)
        
        # If the login session has expired
        if page.locator('xpath=//*[@id="loginerrormessage"]').count() > 0:
            page.locator('xpath=//*[@id="region-main"]/div/div/div/div/div[4]/a[1]').click()
        
        # Crawling the assignment list
        container = page.locator('//div[@data-region="event-list-container"]')
        container.scroll_into_view_if_needed()
        
        page.locator(ASSIGNMENT_SELECTOR).is_visible(timeout=10000)
        assignments = page.locator(ASSIGNMENT_SELECTOR).all()
        return assignments
