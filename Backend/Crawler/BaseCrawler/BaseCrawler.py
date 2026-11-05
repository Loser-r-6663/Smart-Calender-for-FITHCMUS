import time
from pathlib import Path
from contextlib import contextmanager
import html2text
from pydantic import BaseModel


# HTML2Text configuration
_h2t = html2text.HTML2Text()
_h2t.ignore_images = True
_h2t.body_width = 0


class RawTask(BaseModel):
    Title: str = "N/A"           # Title of the post
    Type: str = "N/A"            # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    Description: str = "N/A"     # Description or brief summary of the post
    CreateDate: str = "N/A"      # Creation date of the post
    Duration: str = "N/A"        # Duration of the task or event
    Deadline: str = "N/A"        # Assignment deadline
    Course: str = "N/A"          # Course associated with the post
    Content: str = "N/A"         # Full content of the post
    Link: str = "N/A"            # Link to the original post
    
    def __repr__(self):
        value = f"\nRawTask(\n" \
        f"\tTitle: {self.Title.__repr__()}\n" \
        f"\tType: {self.Type.__repr__()}\n" \
        f"\tDescription: {self.Description.__repr__()}\n" \
        f"\tCreateDate: {self.CreateDate.__repr__()}\n" \
        f"\tDuration: {self.Duration.__repr__()}\n" \
        f"\tDeadline: {self.Deadline.__repr__()}\n" \
        f"\tCourse: {self.Course.__repr__()}\n" \
        f"\tContent: {self.Content.__repr__()}\n" \
        f"\tLink: {self.Link.__repr__()}\n" \
        ")\n"
        return value


class BaseCrawler():
    def __init__(self):
        self.crawler = None
        
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
    
    def set_last_post(self, raw_tasks: list[RawTask]):
        """Update the history file with the link of the most recent task."""
        if self.history_file and raw_tasks and (link := raw_tasks[-1].Link):
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
            
            driver = driver[0] if isinstance(driver, tuple) else driver
            raw_tasks: list[RawTask] = self.browse_page(driver)
            self.set_last_post(raw_tasks)
        return raw_tasks
