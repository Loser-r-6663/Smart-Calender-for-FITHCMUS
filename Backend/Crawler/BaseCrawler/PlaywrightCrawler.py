import json
from pathlib import Path
from contextlib import contextmanager

from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from playwright.sync_api import sync_playwright, Playwright, Page


class PlaywrightCrawler(BaseCrawler):
    def __init__(self):
        self.crawler: Playwright = None
    
    @contextmanager
    def load_engine(self):
        with sync_playwright() as p:
            yield p
    
    def get_state(self):
        """Check if the storage state file is valid and not expired
        Returns:
            cookies (dict): A dictionary of cookies if the state file is valid, otherwise None
        """
        if not (self.state_file and (path := Path(self.state_file)).is_file()):
            return None
        
        state: dict[str, list[dict[str, int|str]]] = json.loads(path.read_text(encoding="utf-8"))
        return {cookie["name"]: cookie for cookie in state.get("cookies", [])}
    
    def check_state(self, cookies: dict[str, dict[str, int | str]] | None):
        """Check if the storage state file is valid and not expired
        Returns:
            - is_valid (bool): True if the state file is valid, otherwise False
            - browser_settings (dict, None): The ways to launch the browser if the state file is invalid
        """
        return True, None
    
    def login(self, settings: dict | None = None):
        """Login to the website and save the login state to a file"""
    
    def authenticate(self):
        print(f"🌐 Checking login state for {self.__class__.__name__}...")
        
        cookies = self.get_state()
        is_valid, settings = self.check_state(cookies)
        if not is_valid:
            self.login(settings)
        
        print(f"🌐 Login state for {self.__class__.__name__} is valid.")
    
    def launch_engine(self, url, settings: dict = {}):
        headless = settings.get("headless", True)
        storage_state = settings.get("storage_state", self.state_file)
        
        browser = self.crawler.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        
        page.goto(url,wait_until='domcontentloaded')
        return page, context, browser
    
    def browse_page(self, page: Page):
        """Browse the page and extract the required data"""
