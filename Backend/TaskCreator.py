import os
import traceback
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
    
    def crawl_raw_tasks(self, crawlers: dict[str, BaseCrawler]):
        """Start the crawling process"""
        raw_tasks: list[RawTask] = []
        for platform, crawler in crawlers.items():
            try:
                # Fetch data from the crawler and update the platform and updated_at fields
                for task in crawler.fetch_data():
                    raw_tasks.append(task.update(platform=platform, updated_at=datetime.now()))
            except AssertionError:
                traceback.print_exc()
                if self.user and platform in ("Portal", "Moodle"): setattr(self.user, f"{platform.lower()}_status", False)
            except:
                print(f"An error occurred while crawling {platform} data:")
                traceback.print_exc()
        return raw_tasks
    
    def parse_tasks(self, raw_tasks: list[RawTask]):
        """Parse the raw tasks and extract structured information"""
        extracted_tasks: list[ExtractedTask] = []
        total_raw = len(raw_tasks)
        for i, task in enumerate(raw_tasks, start=1):
            if task.platform == "Portal":
                tasks = [ExtractedTask.from_raw_task(task)]
            else:
                tasks = [
                    t.update(
                        user_id=self.user.id if self.user else None,
                        source_url=task.link,
                        source_platform=task.platform,
                        updated_at=task.updated_at
                    )
                    for t in Parser.parse(task) if t
                ]
            extracted_tasks.extend(tasks)
            print(f"[{i}/{total_raw}] {task.platform}: +{len(tasks)} task (tổng: {len(extracted_tasks)})")
        return extracted_tasks
    
    def create_task(self):
        """Create structured data from website data"""
        raw_tasks = self.crawl_raw_tasks(self.crawlers(self.user))
        extracted_tasks = self.parse_tasks(raw_tasks)
        return extracted_tasks
