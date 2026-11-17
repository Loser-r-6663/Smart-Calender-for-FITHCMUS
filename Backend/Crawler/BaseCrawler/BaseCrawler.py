import time
import html2text
from contextlib import contextmanager

from apify import Actor
from apify.storages import KeyValueStore

from Backend.Regulation.RawTask import RawTask
from playwright.sync_api import Page, BrowserContext, Browser
from bs4 import BeautifulSoup


# HTML2Text configuration
_h2t = html2text.HTML2Text()
_h2t.ignore_images = True
_h2t.body_width = 0


class BaseCrawler():
    def __init__(self):
        self.crawler = None
        
        self.state_file: str
        self.history_key: str | None = None
        self.home_url: str
    
    @staticmethod
    def convert_to_markdown(html: str):
        """Convert HTML content to Markdown format."""
        return _h2t.handle(html)
    
    @staticmethod
    def time_is_expired(expiration_time: int, buffer: int = 60):
        """Check if the given expiration time has passed, considering a buffer in seconds."""
        return expiration_time < time.time() + buffer
    
    def get_last_post(self):
        """Retrieve the last crawled task from the history file."""
        if self.history_key:
            store: KeyValueStore = Actor.open_key_value_store(name="History")
            return store.get_value(self.history_key)
        
    def set_last_post(self, raw_tasks: list[RawTask]):
        """Update the history file with the link of the most recent task."""
        if self.history_key and (lastlink := raw_tasks[-1].link):
            store: KeyValueStore = Actor.open_key_value_store(name="History")
            store.set_value(self.history_key, lastlink)
    
    @contextmanager
    def load_engine(self):
        """Context manager to load the appropriate crawling engine."""
        yield None
    
    def authenticate(self):
        """Authenticate the crawler if necessary."""
    
    def launch_engine(self, url: str) -> tuple[Page, BrowserContext, Browser] | BeautifulSoup:
        """Launch the crawling engine with the given URL."""
    
    def browse_page(self, page):
        """Browse the page and extract the required data."""
    
    def fetch_data(self):
        """Fetch data from the website"""
        with self.load_engine() as crawler:
            self.crawler = crawler
            
            # Check if the crawler requires authentication and perform it if needed
            self.authenticate()
            
            # Launch the crawling engine and browse the page to extract data
            print(f"🌐 Starting to scrape data from {self.__class__.__name__}...")
            driver = self.launch_engine(self.home_url)
            
            self.last_post = self.get_last_post()
            print(f"🌐 Last crawled task: {self.last_post}\n")
            
            browser = driver[2] if isinstance(driver, tuple) else None
            driver = driver[0] if isinstance(driver, tuple) else driver
            try:
                raw_tasks: list[RawTask] = self.browse_page(driver)
                self.set_last_post(raw_tasks)
            finally:
                if browser: browser.close()
        return raw_tasks
