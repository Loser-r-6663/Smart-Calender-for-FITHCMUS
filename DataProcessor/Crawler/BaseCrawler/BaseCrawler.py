import os
import time
import html2text
from pathlib import Path
from contextlib import contextmanager

from DataProcessor.Standardization.RawTask import RawTask
from playwright.sync_api import Page, BrowserContext, Browser
from bs4 import BeautifulSoup
from DataProcessor.utils.apify_storage import *


# HTML2Text configuration
_h2t = html2text.HTML2Text()
_h2t.ignore_images = True
_h2t.body_width = 0


class BaseCrawler():
    def __init__(self):
        self.crawler = None
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
            if os.environ.get("APP_ROLE") == "SERVER":
                return kv_get(store_name="History", key=self.history_key, default=None)
            
            elif (path := Path(f"DataProcessor/Crawler/History/{self.history_key}.txt")).is_file():
                return path.read_text(encoding="utf-8").strip()
        
    def set_last_post(self, raw_tasks: list[RawTask]):
        """Update the history file with the link of the most recent task."""
        if self.history_key and raw_tasks and (lastlink := raw_tasks[-1].link):
            if os.environ.get("APP_ROLE") == "SERVER":
                kv_set(store_name="History", key=self.history_key, value=lastlink)

            else:
                history_file = f"DataProcessor/Crawler/History/{self.history_key}.txt"
                Path(history_file).write_text(lastlink, encoding="utf-8")
    
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
            
            driver = driver[0] if isinstance(driver, tuple) else driver
            raw_tasks: list[RawTask] = self.browse_page(driver)
            self.set_last_post(raw_tasks)
        return raw_tasks
