import os
import json
from pathlib import Path
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Playwright, Page

from DataProcessor.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from DataProcessor.utils.apify_storage import *

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class PlaywrightCrawler(BaseCrawler):
    def __init__(self):
        self.crawler: Playwright = None
        self.state_key: str | None = None
    
    @contextmanager
    def load_engine(self):
        with sync_playwright() as p:
            yield p
    
    def get_state(self):
        """Check if the storage state file is valid and not expired
        Returns:
            cookies (dict): A dictionary of cookies if the state file is valid, otherwise None
        """
        state: dict[str, list[dict]] = {}
        if self.state_key:
            if os.environ.get("APP_ROLE") == "SERVER":
                state = kv_get(store_name="State", key=self.state_key, default=None)
            
            elif (path := Path(f"DataProcessor/Crawler/State/{self.state_key}.json")).is_file():
                state = json.loads(path.read_text(encoding="utf-8"))
            
        return state
    
    def check_state(self):
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
        
        self.state = self.get_state()
        is_valid, settings = self.check_state()
        if not is_valid:
            self.login(settings)
        
        print(f"🌐 Login state for {self.__class__.__name__} is valid.")
    
    def launch_engine(self, url, settings: dict = {}):
        headless = settings.get("headless", True)
        storage_state = settings.get("storage_state", self.state)
        
        browser = self.crawler.chromium.launch(
            headless = headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            storage_state=storage_state
        )
        page = context.new_page()
        
        page.goto(url, wait_until='domcontentloaded')
        return page, context, browser
    
    def browse_page(self, page: Page):
        """Browse the page and extract the required data"""
