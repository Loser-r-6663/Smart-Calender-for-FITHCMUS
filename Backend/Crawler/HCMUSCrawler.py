from Backend.Crawler.BaseCrawler import PlaywrightCrawler, BeautifulSoupCrawler
from dotenv import load_dotenv
import os

class HCMUSCrawler(BeautifulSoupCrawler):
    def __init__(self):
        super().__init__()
        self.home_url = (
            "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/"
        )
        self.crawl_limit = 5  # Only crawl the 5 earliest posts

    def parse(self, soup):
        news_list = []
        temp_posts = []

        # Get list of posts from the news homepage through <article>
        articles = soup.select("article")
        print(f"Found {len(articles)} posts in {self.home_url}\nCrawling up to {self.crawl_limit} posts...")

        posts_crawled = 0
        for article in articles:
            if posts_crawled >= self.crawl_limit:
                break
            try:
                # Get news title and url from <a> in <h2>
                title_element = article.select_one("h2.cmsmasters_archive_item_title a")
                if not title_element:
                    continue
                title = title_element.get_text(strip=True)
                url = title_element.get("href", "")

                # Get general_info
                general_info_element = article.select_one("div.cmsmasters_archive_item_content p")
                general_info = (general_info_element.get_text(strip=True) if general_info_element else "")

                # Get post date
                date_element = article.select_one("abbr.published.cmsmasters_archive_item_date")
                date_str = (date_element.get_text(strip=True) if date_element else "")

                # Get author
                author_element = article.select_one("span.cmsmasters_archive_item_user_name a")
                author = (author_element.get_text(strip=True) if author_element else "")

                temp_posts.append({
                    "title": title,
                    "url": url,
                    "general_info": general_info,
                    "date": date_str,
                    "author": author,
                })
                posts_crawled += 1

            except Exception as e:
                print(f"Error when parsing article item on homepage: {e}")
                continue

        # Crawl the news information pages
        for post in temp_posts:
            try:
                print(f"Crawling detail: {post['url']}")
                # Access the news information page
                event_soup = self.get_soup(post["url"])

                # Get the news information
                content_element = event_soup.select_one("div.cmsmasters_post_content.entry-content")
                new_info = (content_element.get_text(strip=True) if content_element else "")

                # Add to the real news list
                news_list.append({
                    "title": post["title"],
                    "url": post["url"],
                    "general_info": post["general_info"],
                    "date": post["date"],
                    "author": post["author"],
                    "info": new_info,
                })

            except Exception as e:
                print(
                    f"Error when crawling a news information page with url {post['url']}: {e}"
                )
                continue

        return news_list