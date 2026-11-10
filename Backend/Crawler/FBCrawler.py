from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
import os

LOGIN_NOTIFICATION = 'xpath=//div[contains(@aria-label,"Log in to Facebook")]'
POST_SELECTOR = 'xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div'
POST_CRAWL_ZONE_SELECTOR = 'xpath=/div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div'
CONTENT_CONTAINER_SELECTOR = 'xpath=//div[3]/div/div/div/div/div/span/div'
READ_MORE_BUTTON_SELECTOR = 'xpath=//div[contains(@role,"button")]'
TIME_ELEMENT_CONTAINER_SELECTOR = 'xpath=/div[2]/div/div[2]/div/div[2]/span/div//span[a]/div[2]'
HREF_SELECTOR = 'xpath=/div[2]/div/div[2]/div/div[2]/span/div//span[a]//a'
LINK_ELEMENT_SELECTOR = 'xpath=//a[contains(@href, "/posts/") or contains(@href, "/permalink/") or contains(@href, "/story.php") or contains(@href, "/photos/") or contains(@href, "/videos/")]'


class FBCrawler(PlaywrightCrawler):
    def __init__(self):
        self.history_file = "Backend/Crawler/History/FBHistory.txt"
        self.state_file = "Backend/Crawler/State/FBState.json"
        self.home_url = "https://www.facebook.com/VNUHCM.US"
        self.crawl_limit = 10
    
    def check_state(self, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}
        
        settings = {"headless": True, "storage_state": self.state_file}
        try:
            self.login(settings)
            return True, settings
        except ConnectionError:
            return False, {"headless": False, "storage_state": self.state_file}
    
    def login(self, settings):
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        # Initialize login checking variable
        try:
            page.wait_for_selector(LOGIN_NOTIFICATION,state='visible',timeout=1000)
        except Exception as e:
            browser.close()
            return
        login_notification = page.locator(LOGIN_NOTIFICATION)
        
        # Login required if the login notification is present
        if login_notification.count() > 0:
            if settings["headless"]:
                raise ConnectionError("please log in manually")
            
            # Semi-automatic login process for headed mode (headless=False)
            load_dotenv()
            username = os.getenv("FB_USERNAME")
            password = os.getenv("FB_PASSWORD")
            page.locator('xpath=//input[contains(@name,"email") and contains(@tabindex,"0")]').fill(username)
            page.locator('xpath=//input[contains(@name,"pass") and contains(@dir,"ltr") and not(@placeholder)]').fill(password)
            page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]').click()
            
            # 2-step verification, wait until the user enters the code sent via email
            page.wait_for_selector('xpath=//div[not(@aria-hidden) and contains(@role,"button") and contains(@aria-label,"Thông báo")]',timeout=300000)
            
            # Store state file and close browser
            context.storage_state(path=self.state_file)
            browser.close()
    
    def browse_page(self, page):
        page.wait_for_selector(POST_SELECTOR, state='visible')
        
        raw_tasks: list[RawTask] = []
        for post_crawled in range(1, self.crawl_limit + 1):
            
            # Define xpath to current post
            current_post_xpath = f'{POST_SELECTOR}[{post_crawled}][node() and not(@class)]'
            
            # Check final post
            if page.locator(current_post_xpath).count() == 0:
                # Try scrolling down to see if Facebook loads more posts
                page.evaluate("window.scrollBy(0, 800);")
                page.wait_for_timeout(2000)
                if page.locator(current_post_xpath).count() == 0:
                    break
            
            try:
                # Define raw task
                raw_task = RawTask()
                
                # Get post
                post = page.locator(current_post_xpath)
                post.scroll_into_view_if_needed()
                
                # Get specific crawl zone in a post since html structure very complicated
                post_crawl_zone = post.locator(POST_CRAWL_ZONE_SELECTOR)
                post_crawl_zone.scroll_into_view_if_needed()
                if post_crawl_zone.count() == 0:
                    raise Exception(f"Unable to find post crawl zone for post no.{post_crawled}")
                
                # Content container div tag
                content_container = post_crawl_zone.locator(CONTENT_CONTAINER_SELECTOR)
                content_container.scroll_into_view_if_needed()
                if content_container.count() == 0:
                    raise Exception(f"Unable to find content container for post no.{post_crawled}")
                
                # Handle "read more button"
                read_more_button = content_container.locator(READ_MORE_BUTTON_SELECTOR)
                if read_more_button.count() > 0:
                    read_more_button.first.scroll_into_view_if_needed()
                    read_more_button.first.click()
                    page.wait_for_timeout(1000)
                
                # Get content
                raw_task.Content = self.convert_to_markdown(content_container.inner_html())
                
                # Get time element container (it holds the link and time of the post)
                time_element_container = post_crawl_zone.locator(TIME_ELEMENT_CONTAINER_SELECTOR)
                time_element_container.scroll_into_view_if_needed()
                
                if time_element_container.count() > 0:
                    
                    # Get time
                    raw_task.CreateDate = time_element_container.inner_text()
                    
                    # Find <a> tag(s)
                    link_element = post_crawl_zone.locator(HREF_SELECTOR)
                    
                    if link_element.count() == 0:
                        # NOTE: Fallback and do second try (will mostly fail)
                        link_element = post_crawl_zone.locator(LINK_ELEMENT_SELECTOR)
                    
                    if link_element.count() > 0:
                        
                        # Get target link (may have many <a> tags but the first one shall hold the post link)
                        target_link = link_element.first
                        
                        # The <a> tag that holds the post link has a unique mechanic. Only when you hover the mouse on the time area of the post, does the post link appear in the href attribute. If not, the href attribute would just contain a chaotic string of characters
                        target_link.scroll_into_view_if_needed()
                        target_link.hover()
                        
                        # Get the attribute (href)
                        href = target_link.get_attribute("href")
                        
                        if href:
                            # Clean the post link
                            full_url = urljoin(self.home_url, href)
                            parsed_url = urlparse(full_url)
                            clean_link = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                            
                            # Keep the 'fbid' query parameter if it is a special type of image/video link.
                            if parsed_url.query and ("fbid" in parsed_url.query or "story_fbid" in parsed_url.query):
                                clean_link = f"{clean_link}?{parsed_url.query}"
                            
                            raw_task.Link = clean_link.rstrip('/')
                    else:
                        raise Exception(f"Unable to find link for post no.{post_crawled}")
                else:
                    raise Exception(f"Unable to find time container for post no.{post_crawled}")
                
                # Check if the post has already been scraped during the previous scraping session
                if self.last_post and raw_task.Link == self.last_post: break
                
                # Add to result
                raw_tasks.append(raw_task)
            except Exception: pass
        
        return raw_tasks[::-1]