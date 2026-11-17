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
        os.makedirs("Backend/Crawler/History", exist_ok=True)
        os.makedirs("Backend/Crawler/State", exist_ok=True)
        
        self.user = user
        if user:
            self.personal_crawlers: dict[str, BaseCrawler] = {
                "Portal": PortalCrawler(user),
                "Moodle": MoodleCrawler(user)
            }
        self.public_crawlers: dict[str, BaseCrawler] = {
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
                self.user[f"{platform.lower()}_status"] = False
            except:
                print(f"An error occurred while crawling {platform} data:")
                traceback.print_exc()
        return raw_tasks
    
    def parse_tasks(self, raw_tasks: list[RawTask]):
        """Parse the raw tasks and extract structured information"""
        extracted_tasks: list[ExtractedTask] = []
        len_raw_tasks = len(raw_tasks)
        for task in raw_tasks:
            # Use the Parser to extract structured information (not needed for Portal)
            if task.platform == "Portal":
                extracted_tasks.append(ExtractedTask.from_raw_task(task))
            else:
                for extracted_task in Parser.parse(task):
                    try:
                        if extracted_task:
                            extracted_tasks.append(
                                extracted_task.update(
                                    source_url=task.link,
                                    source_platform=task.platform,
                                    updated_at=task.updated_at
                                )
                            )
                            print(f"Extracted {len(extracted_tasks)} / {len_raw_tasks} tasks from {task.platform}")
                    except Exception:
                        continue
        return extracted_tasks
    
    def create_task(self):
        """Create structured data from website data"""
        raw_tasks = self.crawl_raw_tasks(
            self.personal_crawlers if self.user else self.public_crawlers
        )
        extracted_tasks = self.parse_tasks(raw_tasks)
        return extracted_tasks
