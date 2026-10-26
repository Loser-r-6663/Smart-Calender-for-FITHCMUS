from Backend.Crawler.BaseCrawler import BeautifulSoupCrawler


class FITCrawler(BeautifulSoupCrawler):
    def __init__(self):
        super().__init__()
        self.state_file = "Backend/Crawler/State/FITState.txt"
        self.home_url = "https://www.ctda.hcmus.edu.vn/vi/thong-bao/"
    
    def parse(self, soup):
        raw_tasks = []
        
        events = soup.select("article")
        for event in events:
            raw_task = {"Title": "N/A", "Link": "N/A"}
            
            title = event.select_one("div.post-title a").get_text(strip=True)
            brief = event.select_one("div.post-excerpt").get_text(strip=True)
            link = event.select_one("div.post-title a")["href"]
            
            event_soup = self.get_soup(link)
            content = event_soup.select_one("section.has_content > div > div").decode_contents()
            markdown_content = self.convert_to_markdown(content)
            
            raw_task["Title"] = title
            raw_task["Brief"] = brief
            raw_task["Link"] = link
            raw_task["Content"] = markdown_content
            
            raw_tasks.append(raw_task)
        return raw_tasks
