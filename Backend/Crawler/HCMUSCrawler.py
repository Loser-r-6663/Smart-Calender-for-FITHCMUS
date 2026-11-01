from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.BeautifulSoupCrawler import BeautifulSoupCrawler


class HCMUSCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/HCMUSHistory.txt"
        self.home_url = "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/"
    
    def browse_page(self, page):
        raw_tasks: list[RawTask] = []
        
        articles = page.select("article")
        for article in articles:
            try:
                raw_task = RawTask()
                
                title_element = article.select_one("h2.entry-title a")
                link = title_element["href"]
                
                # Reached the last crawled post. Stopping further crawling
                if self.last_post and link == self.last_post: break
                
                raw_task.Link = link
                raw_task.Title = title_element.get_text(strip=True)
                raw_task.Description = article.select_one("div.entry-content p").get_text(strip=True)
                raw_task.Date = article.select_one("abbr.published").get_text(strip=True)
                
                post_page = self.launch_engine(link)
                content = post_page.select_one("div.entry-content").decode_contents()
                raw_task.Content = self.convert_to_markdown(content)
                
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing article item on HCMUS homepage: {e}")
        
        return raw_tasks[::-1]