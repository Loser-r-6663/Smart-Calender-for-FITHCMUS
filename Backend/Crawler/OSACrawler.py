from Backend.Crawler.BaseCrawler import PlaywrightCrawler, expect, convert_to_markdown
import re


class OSACrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = None
        self.home_url = "https://ctsv.hcmus.edu.vn/info/"
    
    def interact(self, page):
        page.goto(self.home_url, wait_until="networkidle")
        raw_tasks = []
        
        articles = page.locator('div.cursor-pointer.h-full').all()
        for article in articles:
            raw_task = {"Title": "N/A", "Link": "N/A", "Type": "N/A", "Date": "N/A", "Content": "N/A"}
            
            try:
                title = article.locator('h3 > span:nth-child(1)')
                raw_task["Title"] = title.inner_text()
                
                type = article.locator('div.top-3.left-3')
                raw_task["Type"] = type.inner_text()
                
                date = article.locator('h3 span span')
                raw_task["Date"] = date.inner_text()
                
                article.click()
                raw_task["Link"] = page.url
                
                content_element = page.locator('div.hcmus-content')
                expect(content_element).to_have_text(re.compile(r".+"))
                raw_task["Content"] = convert_to_markdown(content_element.inner_html())
                
                page.go_back()
            except Exception as e:
                print(f"Error when parsing article item on OSA: {e}")
            
            raw_tasks.append(raw_task)
        return raw_tasks