from Backend.Crawler.BaseCrawler.BeautifulSoupCrawler import BeautifulSoupCrawler


class FITCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/FITHistory.txt"
        self.home_url = "https://www.ctda.hcmus.edu.vn/vi/thong-bao/"
    
    def browse_page(self, page):
        raw_tasks = []
        
        posts = page.select("article")
        for post in posts:
            raw_task = {"Title": "N/A", "Brief": "N/A", "Link": "N/A", "Content": "N/A"}
            
            try:
                link = post.select_one("div.post-title a")["href"]
                
                # Reached the last crawled post. Stopping further crawling
                if self.last_post and link == self.last_post: break
                raw_task["Link"] = link
                
                title = post.select_one("div.post-title a").get_text(strip=True)
                raw_task["Title"] = title
                
                brief = post.select_one("div.post-excerpt").get_text(strip=True)
                raw_task["Brief"] = brief
                
                post_page = self.launch_engine(link)
                content = post_page.select_one("section.has_content > div > div").decode_contents()
                markdown_content = self.convert_to_markdown(content)
                raw_task["Content"] = markdown_content
            except Exception as e:
                print(f"Error when parsing post item on FIT homepage: {e}")
            
            raw_tasks.append(raw_task)
        return raw_tasks[::-1]
