from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler, RawTask
from Backend.Crawler.BaseCrawler.BeautifulSoupCrawler import HTTPResponse, urlopen
import json


class OSACrawler(BaseCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/OSAHistory.txt"
        self.home_url = "https://ctsv.hcmus.edu.vn/api/news/latest?limit=10"
    
    def launch_engine(self, url: str):
        response: HTTPResponse = urlopen(url)
        data = json.loads(response.read().decode())
        response.close()
        return data["data"]
    
    def browse_page(self, articles: list[dict[str, str]]):
        raw_tasks: list[RawTask] = []
        
        for article in articles:
            try:
                raw_task = RawTask()
                
                link = "https://ctsv.hcmus.edu.vn/news/" + article["slug"]
                if link == self.last_post: break
                
                raw_task.Link = link
                raw_task.Title = article["title"]
                raw_task.Description = article["summary"]
                raw_task.CreateDate = article["createdAt"]
                raw_task.Type = article["category"]["name"]
                raw_task.Content = self.convert_to_markdown(article["content"])
                
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing article item on HCMUS homepage: {e}")
        
        return raw_tasks[::-1]