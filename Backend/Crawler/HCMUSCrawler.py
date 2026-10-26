from Backend.Crawler.BaseCrawler import PlaywrightCrawler
from dotenv import load_dotenv
import os


class HCMUSCrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/HCMUSState.json"
        self.home_url = "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/"
        self.crawl_limit = 5 # Only crawl 5 latest posts

    def login(self,p,state_file):
        if state_file["NotFound"] or state_file["AllExpires"]:
            browser=p.chromium.launch(headless=False)
            context=browser.new_context()
            page=context.new_page()

            page.goto(self.home_url)

            page.wait_for_url(self.home_url, timeout=10000)
            page.wait_for_load_state("networkidle")

            context.storage_state(path=self.state_file)
            browser.close()
    
    def interact(self, page):
        # Access the news homepage
        page.goto(self.home_url,wait_until="networkidle")
        # Temporary result
        temp_posts=[]
        # Real result
        news_list=[]

        # Crawl news homepage
        article_elements = page.locator('xpath=//article[contains(@id, "post-")]').all()
        print(f"Found {len(article_elements)} posts in {self.home_url}\nCrawling {self.crawl_limit} posts...")
        posts_crawled = 0
        for article in article_elements:
            if posts_crawled > self.crawl_limit:
                break
            try:
                # Get title and url from <a> in <h2> in <article>
                title_locator = article.locator('xpath=.//h2[contains(@class, "cmsmasters_archive_item_title")]//a')
                title = title_locator.inner_text().strip() if title_locator.count() > 0 else ""
                url = title_locator.get_attribute("href") if title_locator.count() > 0 else ""
                
                # Get general info of the new
                general_info_locator = article.locator('xpath=.//div[contains(@class, "cmsmasters_archive_item_content")]//p')
                general_info = general_info_locator.inner_text().strip() if general_info_locator.count() > 0 else ""
                
                # Get date
                date_locator = article.locator('xpath=.//abbr[contains(@class, "published cmsmasters_archive_item_date")]')
                date_str = date_locator.inner_text().strip() if date_locator.count() > 0 else ""
                
                # Get author
                author_locator = article.locator('xpath=.//span[contains(@class, "cmsmasters_archive_item_user_name")]//a')
                author = author_locator.inner_text().strip() if author_locator.count() > 0 else ""
                
                # Add to temporary result list
                temp_posts.append({
                    "title": title,
                    "url": url,
                    "general_info": general_info,
                    "date": date_str,
                    "author": author,
                })
                posts_crawled+=1

            except Exception as e:
                print(f"Error when crawling the news homepage: {e}")
                continue

        # Crawl news information pages
        for post in temp_posts:
            try:
                # Access the news information page
                page.goto(post["url"])

                # Get the news info
                content_locator=page.locator('xpath=//div[contains(@class,"cmsmasters_post_content entry-content")]')
                new_info=content_locator.inner_text().strip() if content_locator.count() > 0 else ""

                # Add to real result list
                news_list.append({
                    "title": post["title"],
                    "url": post["url"],
                    "general_info": post["general_info"],
                    "date": post["date"],
                    "author": post["author"],
                    "info": new_info
                })

            except Exception as e:
                print(f"Error when crawling a news information page with url {post["url"]}: {e}")
                continue
                
        return news_list