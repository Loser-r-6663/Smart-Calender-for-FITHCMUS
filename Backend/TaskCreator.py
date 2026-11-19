import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from Backend.Regulation.RawTask import RawTask
from Backend.Regulation.ExtractedTask import ExtractedTask
from Backend.Regulation.User import User

from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler
from Backend.Crawler.FBCrawlers import *

from Backend.Parser.Parser import Parser


class TaskCreator():
    def __init__(self, user: User | None = None):
        if os.environ.get("APP_ROLE") != "SERVER":
            os.makedirs("Backend/Crawler/History", exist_ok=True)
            os.makedirs("Backend/Crawler/State", exist_ok=True)
        
        self.user = user
        self.crawlers = lambda user: {
            "Portal": PortalCrawler(user),
            "Moodle": MoodleCrawler(user)
        } if user else {
            "Khoa Công nghệ thông tin": FITCrawler(),
            "Trường đại học Khoa học tự nhiên": HCMUSCrawler(),
            "Phòng Công tác sinh viên": OSACrawler(),
            "VNUHCMUS": FBCrawler_VNUHCMUS(),
            "Đoàn trường Khoa học tự nhiên": FBCrawler_YUHCMUS(),
            "Đoàn khoa - Liên chi hội khoa Môi trường": FBCrawler_YUE(),
            "Đoàn khoa - Liên chi hội khoa Hóa học": FBCrawler_YUC(),
            "Đoàn khoa - Liên chi hội khoa Sinh học": FBCrawler_YUB(),
            "Đoàn khoa - Liên chi hội khoa Địa chất": FBCrawler_YUG(),
            "Đoàn khoa - Liên chi hội khoa Vật lý": FBCrawler_YUP(),
            "Facebook Khoa Công nghệ thông tin": FBCrawler_FIT()
        }
    
    def _crawl_one(self, platform: str, crawler: BaseCrawler):
        try:
            tasks = [
                task.update(platform=platform, updated_at=datetime.now())
                for task in crawler.fetch_data()
            ]
            return platform, tasks, None
        except AssertionError as exc:
            return platform, [], exc
        except Exception as exc:
            return platform, [], exc

    def crawl_raw_tasks(self, crawlers: dict[str, BaseCrawler], max_workers: int = 4):
        """Start the crawling process"""
        raw_tasks: list[RawTask] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(
                self._crawl_one,
                crawlers.keys(),
                crawlers.values(),
            )
            for platform, tasks, error in results:
                if error is not None:
                    traceback.print_exception(error)
                    if isinstance(error, AssertionError):
                        if self.user and platform in ("Portal", "Moodle"):
                            self.user[f"{platform.lower()}_status"] = False
                    else:
                        print(f"An error occurred while crawling {platform} data:")
                raw_tasks.extend(tasks)
        return raw_tasks
    
    def _parse_one(self, task: RawTask):
        if task.platform == "Portal":
            tasks = [ExtractedTask.from_raw_task(task)]
        else:
            tasks = [
                extracted_task.update(
                    user_id=self.user.id if self.user else None,
                    source_url=task.link,
                    source_platform=task.platform,
                    updated_at=task.updated_at
                )
                for extracted_task in Parser.parse(task) if extracted_task
            ]
        return task, tasks

    def parse_tasks(self, raw_tasks: list[RawTask], max_workers: int = 4):
        """Parse the raw tasks and extract structured information"""
        extracted_tasks: list[ExtractedTask] = []
        total_raw = len(raw_tasks)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(self._parse_one, raw_tasks)
            for i, (task, tasks) in enumerate(results, start=1):
                extracted_tasks.extend(tasks)
                print(f"[{i}/{total_raw}] {task.platform}: +{len(tasks)} task (tổng: {len(extracted_tasks)})")
        return extracted_tasks
    
    def create_task(self):
        """Create structured data from website data"""
        raw_tasks = self.crawl_raw_tasks(self.crawlers(self.user))
        extracted_tasks = self.parse_tasks(raw_tasks)
        return extracted_tasks
