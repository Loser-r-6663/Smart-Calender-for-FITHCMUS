import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Playwright, Page
from bs4 import BeautifulSoup
from http.client import HTTPResponse
from urllib.request import Request, urlopen


class BaseCrawler():
    def fetch_data(self):
        """Fetch data from the website"""


class PlaywrightCrawler(BaseCrawler):
    def __init__(self):
        self.state_file: str
    
    def login(self, p: Playwright, state_file: dict[str, bool]):
        """Login to the website and save the login state to a file"""
    
    def check_state(self):
        """Check if the storage state file is valid and not expired
        Returns:
            state_file (dict):
                - NotFound (bool): if the state file does not exist
                - AnyExpires (bool): if any of the cookies in the state file are expired
                - AllExpires (bool): if all of the cookies in the state file are expired
        """
        path = Path(self.state_file)
        compose = lambda i, j, k: {"NotFound": i, "AnyExpires": j, "AllExpires": k}
        if not path.is_file(): return compose(True, True, True)
        
        try:
            with path.open("r", encoding="utf-8") as f:
                state: dict[str, list[dict[str, int]]] = json.load(f)
            
            now = time.time()
            expires_list = [
                cookie.get("expires", -1) != -1 and cookie["expires"] < now + 60
                for cookie in state.get("cookies", [])
            ]
            return compose(False, any(expires_list), all(expires_list))
        
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            return compose(True, True, True)
    
    def fetch_data(self):
        """Fetch data from the website by logging in and interacting with the page"""
        with sync_playwright() as p:
            print(f"Checking login state for {self.__class__.__name__}...")
            self.login(p, self.check_state())
            print(f"Login state for {self.__class__.__name__} is valid. Starting to scrape data...")
            
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=self.state_file)
            page = context.new_page()
            
            raw_task = self.interact(page)
            browser.close()
        return raw_task
    
    def interact(self, page: Page):
        """Interact with the page to fetch the required data"""


class BeautifulSoupCrawler(BaseCrawler):
    def __init__(self):
        self.home_url: str
    
    def fetch_data(self):
        """Download the target page and parse it with BeautifulSoup."""
        soup = self.get_soup(self.home_url)
        return self.parse(soup)
    
    def get_soup(self, url: str):
        """Download the configured URL and return its decoded HTML."""
        request = Request(url, headers={"User-Agent": "UniversityLifeAssistant/1.0"})
        response: HTTPResponse = urlopen(request, timeout=30)
        html = response.read().decode(response.headers.get_content_charset() or "utf-8")
        response.close()
        
        soup = BeautifulSoup(html, "html.parser")
        return soup
    
    def parse(self, soup: BeautifulSoup):
        """Extract and return the required data from the parsed document."""
