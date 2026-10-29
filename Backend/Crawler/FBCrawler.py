from Backend.Crawler.BaseCrawler import PlaywrightCrawler
from dotenv import load_dotenv
import os

class FBCrawler(PlaywrightCrawler):
    def __init__(self):
        self.home_url="https://www.facebook.com/VNUHCM.US"
        self.state_file

    def check_state(self, p, cookies):
        # Copied from MoodleCrawler :))
        if not cookies:
            return False, {"headless": False, "storage_state": None}

        browser_settings = {"headless": True, "storage_state": self.state_file}
        
        try:
            self.login(p, browser_settings)
            return True, browser_settings
        
        except ConnectionError:
            return False, {"headless": False, "storage_state": self.state_file}
    
    def login(self, p, browser_settings):
        # Access the page
        browser, context, page = self.start_browser(p, browser_settings)
        page.goto(self.home_url)

        # Initialize login checking variable (for code thẩm mỹ)
        login_required = False
        login_notification = page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]')
        if login_notification.count() > 0:
            login_required = True

        if login_required:
            if browser_settings["headless"]:
                raise Exception("Thông báo: Code quá ngu nên ko biết cách đăng nhập tự động trong chế độ headless, hãy thử đăng nhập thủ công")
            # Semi-automatic login process for headed mode (headless=False)
            load_dotenv()
            username = os.getenv("FB_USERNAME")
            password = os.getenv("FB_PASSWORD")
            page.locator('xpath=//input[contains(@name,"email") and contains(@tabindex,"0")]').fill(username)
            page.locator('xpath=//input[contains(@name,"pass") and contains(@dir,"ltr")]').nth(1).fill(password)
            page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]').click()

            # 2-step verification, wait until the user enters the code sent via email
            page.wait_for_selector('xpath=//div[not(@aria-hidden) and contains(@role,"button") and contains(@aria-label,"Thông báo")]',timeout=30000)

            # Store state file and close browser
            context.storage_state(path=self.state_file)
            browser.close()
        
    def interact(self, page):
        # Access the page, wait for loading
        page.goto(self.home_url)
        try:
            pass
        except Exception as e:
            print(f"Timeout waiting for posts to load: {e}")
            return []

