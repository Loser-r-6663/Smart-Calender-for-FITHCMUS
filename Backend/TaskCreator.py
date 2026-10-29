import traceback

from Backend.Crawler.BaseCrawler import BaseCrawler
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler


class TaskCreator():
    def __init__(self):
        self.crawlers: dict[str, BaseCrawler] = {
            "Portal": PortalCrawler(),
            "Moodle": MoodleCrawler(),
            "FIT": FITCrawler(),
            "HCMUS": HCMUSCrawler(),
            "OSA": OSACrawler()
        }
    
    def crawl_raw_text(self):
        """Start the crawling process"""
        raw_tasks = {}
        
        for key, crawler in self.crawlers.items():
            try:
                raw_tasks[key] = crawler.fetch_data()
            except Exception:
                print(f"An error occurred while crawling {key} data:")
                traceback.print_exc()
                raw_tasks[key] = []
        
        return raw_tasks
    
    def create_task(self):
        """Create structured data from website data"""
        raw_tasks = self.crawl_raw_text()
        print(raw_tasks)
