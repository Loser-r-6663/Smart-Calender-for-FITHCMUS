import traceback

from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler, RawTask
from Backend.Crawler.PortalCrawler import PortalCrawler
from Backend.Crawler.MoodleCrawler import MoodleCrawler
from Backend.Crawler.FITCrawler import FITCrawler
from Backend.Crawler.HCMUSCrawler import HCMUSCrawler
from Backend.Crawler.OSACrawler import OSACrawler
from Backend.Crawler.FBCrawler import FBCrawler


class TaskCreator():
    def __init__(self):
        self.crawlers: dict[str, BaseCrawler] = {
            "Portal": PortalCrawler(),
            "Moodle": MoodleCrawler(),
            "FIT": FITCrawler(),
            "HCMUS": HCMUSCrawler(),
            "OSA": OSACrawler(),
            "FB": FBCrawler()
        }
    
    def crawl_raw_text(self):
        """Start the crawling process"""
        raw_tasks: dict[str, RawTask] = {}
        
        for key, crawler in self.crawlers.items():
            try:
                raw_tasks[key] = crawler.fetch_data()
            except Exception:
                print(f"An error occurred while crawling {key} data:")
                traceback.print_exc()
                raw_tasks[key] = []
        
        return raw_tasks
    def formatted_print(self, raw_data:dict[str,list[RawTask]], output_file_name:str = "none"):
        file_handle = None
        # Hanling output file
        if output_file_name and output_file_name.lower() != "none": 

            # Check if user has added ".txt" at the end of file name
            if not output_file_name.endswith(".txt"):
                output_file_name += ".txt"
            
            # Open output file
            file_handle = open(output_file_name, "w", encoding="utf-8")

        def custom_print(task:RawTask):
            # Print on the console
            print(task)
            # Print into the output file if it is open
            if file_handle:
                file_handle.write(task)
                file_handle.write("\n")
        try:
            for platform, raw_tasks in raw_data.items():

                task_count = 0
                custom_print(f"=========================(  {platform}  )=========================\n\n")

                for raw_task in raw_tasks:
                    custom_print(f"-------------------------< TASK NUMBER {task_count+1} OF {platform} >-------------------------\n")
                    
                    custom_print(raw_task)
                    
                    task_count += 1
                    custom_print("\n")
        
        finally:
            if file_handle:
                file_handle.close()

    def create_task(self):
        """Create structured data from website data"""
        raw_data = self.crawl_raw_text()
        self.formatted_print(raw_data,"OUTPUT")
