from Backend.Crawler.BaseCrawler import BeautifulSoupCrawler


class HCMUSCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.home_url = "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/"
    
    def parse(self, soup):
        raw_tasks = []
        
        articles = soup.select("article")
        for article in articles:
            raw_task = {"Title": "N/A", "Brief": "N/A", "Link": "N/A", "Date": "N/A", "Content": "N/A"}
            
            # Get the title, brief, and link from the post
            try:
                title_element = article.select_one("h2.entry-title a")
                link = title_element["href"]
                raw_task["Link"] = link
                
                title = title_element.get_text(strip=True)
                raw_task["Title"] = title
                
                brief = article.select_one("div.entry-content p").get_text(strip=True)
                raw_task["Brief"] = brief
                
                date = article.select_one("abbr.published").get_text(strip=True)
                raw_task["Date"] = date
                
                post_soup = self.get_soup(link)
                content = post_soup.select_one("div.entry-content").decode_contents()
                markdown_content = self.convert_to_markdown(content)
                raw_task["Content"] = markdown_content
            except Exception as e:
                print(f"Error when parsing article item on HCMUS homepage: {e}")
            
            raw_tasks.append(raw_task)
        return raw_tasks