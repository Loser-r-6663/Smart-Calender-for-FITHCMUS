from Backend.Crawler.BaseCrawler import BeautifulSoupCrawler


class HCMUSCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.state_file = None
        self.history_file = "Backend/Crawler/History/HCMUSHistory.txt"
        self.home_url = "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/"
    
    def browse_page(self, page):
        raw_tasks = []
        
        articles = page.select("article")
        for article in articles:
            raw_task = {"Title": "N/A", "Brief": "N/A", "Link": "N/A", "Date": "N/A", "Content": "N/A"}
            
            try:
                title_element = article.select_one("h2.entry-title a")
                link = title_element["href"]
                
                # Reached the last crawled post. Stopping further crawling
                if self.last_post and link == self.last_post: break
                raw_task["Link"] = link
                
                title = title_element.get_text(strip=True)
                raw_task["Title"] = title
                
                brief = article.select_one("div.entry-content p").get_text(strip=True)
                raw_task["Brief"] = brief
                
                date = article.select_one("abbr.published").get_text(strip=True)
                raw_task["Date"] = date
                
                post_page = self.launch_engine(link)
                content = post_page.select_one("div.entry-content").decode_contents()
                markdown_content = self.convert_to_markdown(content)
                raw_task["Content"] = markdown_content
            except Exception as e:
                print(f"Error when parsing article item on HCMUS homepage: {e}")
            
            raw_tasks.append(raw_task)
        return raw_tasks[::-1]