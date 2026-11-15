import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin

from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler

LOGIN_NOTIFICATION = 'xpath=//div[contains(@aria-label,"Log in to Facebook")]'
POST_SELECTOR = 'xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[not(@class)]/div'
POST_CRAWL_ZONE_SELECTOR = 'xpath=/div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div'
CONTENT_CONTAINER_SELECTOR = 'xpath=//div[3]/div/div/div/div/div/span/div'
READ_MORE_BUTTON_SELECTOR = 'xpath=//div[contains(@role,"button")]'
TIME_ELEMENT_CONTAINER_SELECTOR = 'xpath=/div[2]/div/div[2]/div/div[2]/span/div//span[a]//div[contains(text(),"Tháng")]'
HREF_SELECTOR = 'xpath=/div[2]/div/div[2]/div/div[2]/span/div//span[a]//a'
LINK_ELEMENT_SELECTOR = 'xpath=//a[contains(@href, "/posts/") or contains(@href, "/permalink/") or contains(@href, "/story.php") or contains(@href, "/photos/") or contains(@href, "/videos/")]'


class FBCrawler(PlaywrightCrawler):
    is_valid = False
    
    def __init__(
        self,
        history_file: str | None = None,
        home_url: str | None = None,
        crawl_limit: int = 10,
    ):
        self.state_file = "Backend/Crawler/State/FBState.json"
        self.history_file = history_file or "Backend/Crawler/History/FBHistory.txt"
        self.home_url = home_url or "https://www.facebook.com/VNUHCM.US"
        self.crawl_limit = crawl_limit
    
    def check_state(self, cookies):
        if not cookies or "c_user" not in cookies:
            return False, {"headless": False, "storage_state": None}
        
        settings = {"headless": True, "storage_state": self.state_file}
        try:
            if not FBCrawler.is_valid:
                self.login(settings)
                FBCrawler.is_valid = True
            return True, settings
        except Exception:
            return False, {"headless": False, "storage_state": None}
    
    def login(self, settings):
        headless = settings.get("headless", True)
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        if headless:
            try:
                page.wait_for_selector(LOGIN_NOTIFICATION, state='visible', timeout=3000)
                browser.close()
                raise ConnectionError("Login required")
            except Exception as e:
                browser.close()
                if isinstance(e, ConnectionError):
                    raise
                return
        
        # Headed mode: Interactive user login
        load_dotenv()
        username = os.getenv("FB_USERNAME")
        password = os.getenv("FB_PASSWORD")
        if (
            username
            and password
            and username not in {"your", "your_fb_username_here"}
            and password not in {"your", "your_fb_password_here"}
        ):
            try:
                page.wait_for_selector('xpath=//input[contains(@name,"email") and contains(@tabindex,"0")]', timeout=5000)
                page.locator('xpath=//input[contains(@name,"email") and contains(@tabindex,"0")]').fill(username)
                page.locator('xpath=//input[contains(@name,"pass") and contains(@dir,"ltr") and not(@placeholder)]').fill(password)
                page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]').click()
            except Exception:
                pass
        else:
            print("ℹ️ Vui lòng đăng nhập / xác minh tài khoản Facebook trên cửa sổ trình duyệt đang mở...")
        
        # Wait until user completes verification/login (c_user cookie set)
        logged_in = False
        for _ in range(300):
            try:
                current_cookies = {c["name"]: c for c in context.cookies()}
                if "c_user" in current_cookies:
                    logged_in = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(1000)
        
        if logged_in:
            page.wait_for_timeout(2000)
            context.storage_state(path=self.state_file)
            FBCrawler.is_valid = True
            print("✅ Đăng nhập Facebook thành công, đã lưu phiên!")
        else:
            print("⚠️ Hết thời gian chờ đăng nhập Facebook.")
        
        browser.close()
    
    def browse_page(self, page):
        try:
            page.wait_for_selector(POST_SELECTOR, state='visible', timeout=10000)
        except Exception:
            return []
        
        raw_tasks: list[RawTask] = []
        for post_crawled in range(1, self.crawl_limit + 1):
            try:
                # Define raw task
                raw_task = RawTask()
                
                # Get post
                post = page.locator(f'{POST_SELECTOR}[{post_crawled}][node() and not(@class)]')
                if post.count() > 0:
                    post.scroll_into_view_if_needed()
                else: break
                
                # Get specific crawl zone in a post and content container
                post_crawl_zone = post.locator(POST_CRAWL_ZONE_SELECTOR)
                content_container = post_crawl_zone.locator(CONTENT_CONTAINER_SELECTOR).nth(0)
                content_container.scroll_into_view_if_needed()
                
                # Find link
                if (link_element := post_crawl_zone.locator(HREF_SELECTOR)).count() == 0:
                    link_element = post_crawl_zone.locator(LINK_ELEMENT_SELECTOR) # NOTE: Fallback and do second try (will mostly fail)
                
                # Get target link
                target_link = link_element.first
                target_link.hover() # NOTE: The <a> tag that holds the post link has a unique mechanic. Only when you hover the mouse on the time area of the post, does the post link appear in the href attribute. If not, the href attribute would just contain a chaotic string of characters
                href = target_link.get_attribute("href")
                
                # Clean the post link
                full_url = urljoin(self.home_url, href)
                parsed_url = urlparse(full_url)
                clean_link = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                
                # Keep the 'fbid' query parameter if it is a special type of image/video link.
                if "fbid" in parsed_url.query:
                    clean_link += '?' + parsed_url.query
                
                raw_task.link = clean_link.rstrip('/')
                
                # Check if the post has already been scraped during the previous scraping session
                if raw_task.link == self.last_post: break
                
                # Handle "read more button"
                read_more_button = content_container.locator(READ_MORE_BUTTON_SELECTOR)
                if read_more_button.count() > 0:
                    read_more_button.first.click()
                
                # Get content
                raw_task.content = self.convert_to_markdown(content_container.inner_html())
                
                # Get time
                time_element_container = post_crawl_zone.locator(TIME_ELEMENT_CONTAINER_SELECTOR)
                raw_task.create_date = time_element_container.inner_text()
                
                # Add to result
                raw_tasks.append(raw_task)
            except Exception as e:
                print(f"Error when parsing post {post_crawled} on FIT homepage: {e}")
        
        return raw_tasks[::-1]
