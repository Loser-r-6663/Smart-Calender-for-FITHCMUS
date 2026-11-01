from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.BeautifulSoupCrawler import BeautifulSoupCrawler


class FITCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/FITHistory.txt"
        self.home_url = "https://www.ctda.hcmus.edu.vn/vi/thong-bao/"
    
    def browse_page(self, page):
        raw_tasks: list[RawTask] = []
        
        posts = page.select("article")
        for post in posts:
            try:
                raw_task = RawTask()
                
                # Reached the last crawled post. Stopping further crawling
                link = post.select_one("div.post-title a")["href"]
                if self.last_post and link == self.last_post: break
                
                raw_task.Link = link
                raw_task.Title = post.select_one("div.post-title a").get_text(strip=True)
                raw_task.Description = post.select_one("div.post-excerpt").get_text(strip=True)
                
                post_page = self.launch_engine(link)
                content = post_page.select_one("section.has_content > div > div").decode_contents()
                raw_task.Content = self.convert_to_markdown(content)
                
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing post item on FIT homepage: {e}")
            
        return raw_tasks[::-1]
