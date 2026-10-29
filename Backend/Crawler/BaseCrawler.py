import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Playwright, Page, expect
from bs4 import BeautifulSoup
from http.client import HTTPResponse
from urllib.request import Request, urlopen
import html2text


class BaseCrawler():
    def fetch_data(self):
        """Fetch data from the website"""


class PlaywrightCrawler(BaseCrawler):
    def __init__(self):
        self.state_file: str
    
    def login(self, p: Playwright, browser_settings: dict | None = None):
        """Login to the website and save the login state to a file"""
    
    def get_state(self):
        """Check if the storage state file is valid and not expired
        Returns:
            cookies (dict): A dictionary of cookies if the state file is valid, otherwise None
        """
        if not self.state_file: return None
        path = Path(self.state_file)
        if not path.is_file(): return None
        
        with path.open("r", encoding="utf-8") as f:
            state: dict[str, list[dict[str, int|str]]] = json.load(f)
            cookies = {i["name"]: i for i in state.get("cookies", [])}
        
        return cookies
    
    def check_state(self, p: Playwright, cookies: dict[str, dict[str, int | str]] | None):
        """Check if the storage state file is valid and not expired
        Returns:
            - is_valid (bool): True if the state file is valid, otherwise False
            - browser_settings (dict, None): The ways to launch the browser if the state file is invalid
        """
        return True, None
    
    def start_browser(self, p: Playwright, browser_settings: dict | None = None):
        """Start a new browser instance with the given settings"""
        if browser_settings is None:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=None)
            page = context.new_page()
        else:
            browser = p.chromium.launch(headless=browser_settings.get("headless", True))
            context = browser.new_context(storage_state=browser_settings.get("storage_state", None))
            page = context.new_page()
        return browser, context, page
    
    def fetch_data(self):
        """Fetch data from the website by logging in and interacting with the page"""
        with sync_playwright() as p:
            print(f"🌐 Checking login state for {self.__class__.__name__}...")
            
            cookies = self.get_state()
            is_valid, browser_settings = self.check_state(p, cookies)
            if not is_valid:
                self.login(p, browser_settings)
            
            print(f"🌐 Login state for {self.__class__.__name__} is valid. Starting to scrape data...")
            
            browser, _, page = self.start_browser(p, {
                "headless": True, "storage_state": self.state_file
            })
            
            raw_task = self.interact(page)
            browser.close()
        return raw_task
    
    def interact(self, page: Page):
        """Interact with the page to fetch the required data"""


class BeautifulSoupCrawler(BaseCrawler):
    def __init__(self):
        self.state_file: str
        self.home_url: str
    
    def fetch_data(self):
        """Download the target page and parse it with BeautifulSoup."""
        print(f"🌐 Starting to scrape data from {self.__class__.__name__}...")
        soup = self.get_soup(self.home_url)
        
        # Get last crawled state from the state file
        last_post = self.get_last_post()
        print(f"🌐 Last crawled post: {last_post}")
        
        raw_tasks = self.parse(soup, last_post)
        self.set_last_post(raw_tasks)
        return raw_tasks
    
    def get_soup(self, url: str):
        """Download the configured URL and return its decoded HTML."""
        request = Request(url, headers={"User-Agent": "UniversityLifeAssistant/1.0"})
        response: HTTPResponse = urlopen(request, timeout=30)
        html = response.read().decode(response.headers.get_content_charset() or "utf-8")
        response.close()
        
        soup = BeautifulSoup(html, "html.parser")
        return soup
    
    def convert_to_markdown(self, html: str):
        """Convert HTML content to Markdown format."""
        h = html2text.HTML2Text()
        h.ignore_images = True
        h.body_width = 0
        markdown_content = h.handle(html)
        return markdown_content
    
    def get_last_post(self):
        """Retrieve the last crawled post from the state file."""
        path = Path(self.state_file)
        if not path.is_file(): return None
        
        with path.open("r", encoding="utf-8") as f:
            post_link = f.read().strip()
        return post_link
    
    def set_last_post(self, raw_tasks: list[dict[str, str]]):
        """Update the state file with the link of the most recent post."""
        if not raw_tasks: return
        
        last_post_link = raw_tasks[-1].get("Link", "")
        if not last_post_link: return
        
        path = Path(self.state_file)
        with path.open("w", encoding="utf-8") as f:
            f.write(last_post_link)
    
    def parse(self, soup: BeautifulSoup, last_post: str):
        """Extract and return the required data from the parsed document."""
