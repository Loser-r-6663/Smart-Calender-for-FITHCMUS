import os
import traceback

from Backend.Regulation.RawTask import RawTask
from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler
from Backend.Crawler.FBCrawlers import FBCrawler_VNUHCMUS, FBCrawler_YUHCMUS, FBCrawler_YUE, FBCrawler_YUC, FBCrawler_YUB, FBCrawler_YUG, FBCrawler_YUP, FBCrawler_FIT


class TaskCreator():
    def __init__(self):
        os.makedirs("Backend/Crawler/History", exist_ok=True)
        os.makedirs("Backend/Crawler/State", exist_ok=True)
        
        self.crawlers: dict[str, BaseCrawler] = {
            # "Moodle": MoodleCrawler(),
            # "FIT": FITCrawler(),
            # "HCMUS": HCMUSCrawler(),
            # "OSA": OSACrawler(),
            "VNUHMCUS": FBCrawler_VNUHCMUS(),
            "YUHCMUS": FBCrawler_YUHCMUS(),
            "YUE": FBCrawler_YUE(),
            "YUC": FBCrawler_YUC(),
            "YUB": FBCrawler_YUB(),
            "YUG": FBCrawler_YUG(),
            "YUP": FBCrawler_YUP(),
            "FBFIT": FBCrawler_FIT()
        }
    
    def crawl_raw_tasks(self):
        """Start the crawling process"""
        # Crawl Portal data
        try:
            courses = PortalCrawler().fetch_data()
        except Exception:
            print(f"An error occurred while crawling Portal data:")
            traceback.print_exc()
        
        # Crawl other platforms data
        raw_tasks: list[RawTask] = []
        for key, crawler in self.crawlers.items():
            try:
                for raw_task in crawler.fetch_data():
                    raw_tasks.append(raw_task.update(Platform=key))
            except Exception:
                print(f"An error occurred while crawling {key} data:")
                traceback.print_exc()
        
        return courses, raw_tasks
    
    def create_task(self):
        """Create structured data from website data"""
        courses, raw_tasks = self.crawl_raw_tasks()
        print(courses + raw_tasks, file=open("Backend/Crawler/RawTasks.txt", "w", encoding="utf-8"))
