import os
import traceback

from Backend.Regulation.Task import RawTask

from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler
from Backend.Crawler.FBCrawler import FBCrawler

from Backend.Parser.Parser import Parser


class TaskCreator():
    def __init__(self):
        os.makedirs("Backend/Crawler/History", exist_ok=True)
        os.makedirs("Backend/Crawler/State", exist_ok=True)
        
        self.crawlers: list[tuple[str, BaseCrawler]] = [
            ("Moodle", MoodleCrawler()),
            ("FIT", FITCrawler()),
            ("HCMUS", HCMUSCrawler()),
            ("OSA", OSACrawler()),
            ("FB", FBCrawler())
        ]
    
    def crawl_raw_tasks(self):
        """Start the crawling process"""
        def try_crawl(platform_name: str, crawler: BaseCrawler) -> list[RawTask]:
            try: return [task.update(Platform=platform_name) for task in crawler.fetch_data()]
            except:
                print(f"An error occurred while crawling {platform_name} data:")
                traceback.print_exc()
                return []
        
        courses = try_crawl("Portal", PortalCrawler())
        raw_tasks = [task for crawler in self.crawlers for task in try_crawl(*crawler)]
        return courses, raw_tasks
    
    def parse_tasks(self, raw_tasks: list[RawTask]):
        """Parse the raw tasks and extract structured information"""
        return [extracted_task for task in raw_tasks if (extracted_task := Parser.parse(task))]
    
    def create_task(self):
        """Create structured data from website data"""
        courses, raw_tasks = self.crawl_raw_tasks()
        extracted_tasks = self.parse_tasks(raw_tasks)
        
        print(extracted_tasks, file=open("ExtractedTasks.txt", "w", encoding="utf-8"))
