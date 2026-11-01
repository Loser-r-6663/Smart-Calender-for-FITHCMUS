import json
import time
from pathlib import Path
from contextlib import contextmanager

from playwright.sync_api import sync_playwright, Playwright, Page
from bs4 import BeautifulSoup
from http.client import HTTPResponse
from urllib.request import Request, urlopen
import html2text


# HTML2Text configuration
_h2t = html2text.HTML2Text()
_h2t.ignore_images = True
_h2t.body_width = 0


class BaseCrawler():
    def __init__(self):
        self.crawler: Playwright | None = None
        
        self.state_file: str
        self.history_file: str
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
        if self.history_file and (path := Path(self.history_file)).is_file():
            return path.read_text(encoding="utf-8").strip()
    
    def set_last_post(self, raw_tasks: list[dict[str, str]]):
        """Update the history file with the link of the most recent task."""
        if self.history_file and raw_tasks and (link := raw_tasks[-1].get("Link")):
            Path(self.history_file).write_text(link, encoding="utf-8")
    
    @contextmanager
    def load_engine(self):
        """Context manager to load the appropriate crawling engine."""
        yield None
    
    def authenticate(self):
        """Authenticate the crawler if necessary."""
    
    def launch_engine(self, url: str):
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
            
            raw_tasks = self.browse_page(driver[0] if isinstance(driver, tuple) else driver)
            self.set_last_post(raw_tasks)
        return raw_tasks


class PlaywrightCrawler(BaseCrawler):
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
        
        page.goto(url, wait_until="networkidle")
        return page, context, browser
    
    def browse_page(self, page: Page):
        """Browse the page and extract the required data"""


class BeautifulSoupCrawler(BaseCrawler):
    def launch_engine(self, url):
        request = Request(url, headers={"User-Agent": "UniversityLifeAssistant/1.0"})
        response: HTTPResponse = urlopen(request, timeout=30)
        html = response.read().decode(response.headers.get_content_charset() or "utf-8")
        response.close()
        
        page = BeautifulSoup(html, "html.parser")
        return page
    
    def browse_page(self, page: BeautifulSoup):
        """Extract and return the required data from the parsed document."""
