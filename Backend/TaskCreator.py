import os
import traceback
from datetime import datetime

from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler, RawTask
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler
from Backend.Crawler.FBCrawler import FBCrawler
from Backend.Crawler.FBCrawlers import (
    FBCrawler_VNUHCMUS,
    FBCrawler_YUHCMUS,
    FBCrawler_YUE,
    FBCrawler_YUC,
    FBCrawler_YUB,
    FBCrawler_YUG,
    FBCrawler_YUP,
    FBCrawler_FIT,
)


class TaskCreator():
    def __init__(self, include_all_fb_pages: bool = False):
        os.makedirs("Backend/Crawler/History", exist_ok=True)
        os.makedirs("Backend/Crawler/State", exist_ok=True)
        
        self.crawlers: dict[str, BaseCrawler] = {
            "Portal": PortalCrawler(),
            "Moodle": MoodleCrawler(),
            "FIT": FITCrawler(),
            "HCMUS": HCMUSCrawler(),
            "OSA": OSACrawler(),
        }
        if include_all_fb_pages:
            self.crawlers.update({
                "VNUHMCUS": FBCrawler_VNUHCMUS(),
                "Đoàn trường Khoa học tự nhiên": FBCrawler_YUHCMUS(),
                "Đoàn khoa - Liên chi hội khoa Môi trường": FBCrawler_YUE(),
                "Đoàn khoa - Liên chi hội khoa Hóa học": FBCrawler_YUC(),
                "Đoàn khoa - Liên chi hội khoa Sinh học": FBCrawler_YUB(),
                "Đoàn khoa - Liên chi hội khoa Địa chất": FBCrawler_YUG(),
                "Đoàn khoa - Liên chi hội khoa Vật lý": FBCrawler_YUP(),
                "Facebook Khoa Công nghệ thôn tin": FBCrawler_FIT(),
            })
        else:
            self.crawlers["FB"] = FBCrawler()
    
    def crawl_raw_task(self) -> dict[str, list[RawTask]]:
        """Start the crawling process, returning results mapped by platform key."""
        raw_tasks: dict[str, list[RawTask]] = {}
        for key, crawler in self.crawlers.items():
            try:
                tasks = crawler.fetch_data()
                # Attach platform and timestamp if not already set
                for task in tasks:
                    if getattr(task, "Platform", None) is None:
                        task.Platform = key
                    if getattr(task, "UpdatedAt", None) is None:
                        task.UpdatedAt = datetime.now()
                raw_tasks[key] = tasks
            except Exception:
                print(f"An error occurred while crawling {key} data:")
                traceback.print_exc()
                raw_tasks[key] = []
        return raw_tasks
    
    def crawl_raw_tasks(self) -> list[RawTask]:
        """Start the crawling process, returning a flat list of tasks."""
        results = self.crawl_raw_task()
        return [task for tasks in results.values() for task in tasks]
    
    def create_task(self):
        """Create raw task data from crawler sources and save to RawTasks.txt."""
        raw_tasks = self.crawl_raw_task()
        with open("Backend/Crawler/RawTasks.txt", "w", encoding="utf-8") as f:
            print(raw_tasks, file=f)
        return raw_tasks
