from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler, Page
from dotenv import load_dotenv
import os

class FBCrawler(PlaywrightCrawler):
    def __init__(self):
        self.history_file = None
        self.home_url = "https://www.facebook.com/VNUHCM.US"
        self.state_file = "Backend/Crawler/State/FBState.json"
        self.crawl_limit = 10
        self.scroll_limit = 2

    def check_state(self, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}

        browser_settings = {"headless": False, "storage_state": self.state_file}
        
        try:
            self.login(browser_settings)
            return True, browser_settings
        
        except ConnectionError:
            return False, {"headless": True, "storage_state": self.state_file}
    
    def login(self, settings):
        # Access the page
        page, context, browser = self.launch_engine(self.home_url, settings)

        # Initialize login checking variable (thẩm mỹ)
        login_required = False
        login_notification = page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]')
        if login_notification.count() > 0:
            login_required = True

        if login_required:
            if settings["headless"]:
                raise ConnectionError("please log in manually")
            # Semi-automatic login process for headed mode (headless=False)
            load_dotenv()
            username = os.getenv("FB_USERNAME")
            password = os.getenv("FB_PASSWORD")
            page.locator('xpath=//input[contains(@name,"email") and contains(@tabindex,"0")]').fill(username)
            page.locator('xpath=//input[contains(@name,"pass") and contains(@dir,"ltr")]').nth(1).fill(password)
            page.locator('xpath=//div[contains(@aria-label,"Log in to Facebook")]').click()

            # 2-step verification, wait until the user enters the code sent via email
            page.wait_for_selector('xpath=//div[not(@aria-hidden) and contains(@role,"button") and contains(@aria-label,"Thông báo")]',timeout=300000)

            # Store state file and close browser
            context.storage_state(path=self.state_file)
            browser.close()

    def scroll_fb_until_post(self,page:Page,post_index:int):
        '''Return bool1, bool2
        # bool1: Found post
        # bool2: Last post reached'''
        # NOTE: Hàm này không hoạt động, đã thử page.evaluate("window.scrollTo(0, document.body.scrollHeight);") và page.mouse.wheel()
        scroll_count = 0
        last_post_reached = False
        while scroll_count < self.scroll_limit:
            page.mouse.move(500, 500)
            page.mouse.wheel(0,1500)
            page.wait_for_timeout(5000)
            try:
                page.wait_for_selector(f'xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[{post_index}][node() and not(@class)]',state='visible',timeout=2000)
                return True,last_post_reached
            except TimeoutError as e:
                print(f"Unable to find post no.{post_index}:{e}")
                scroll_count += 1
        return False, last_post_reached
        
    def browse_page(self, page):
        page.wait_for_selector('xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div',state='visible')

        # Define post count and raw task list
        post_crawled = 0
        raw_tasks = []

        while post_crawled < self.crawl_limit:
            # define raw task
            raw_task = {
                "Time": "N/A",
                "Content": "N/A"
            }
            try:
                # Get post
                post = page.locator(f'xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[{post_crawled+1}][node() and not(@class)]')
                if post.count() == 0:
                    post_found, last_post = self.scroll_fb_until_post(page,post_crawled+1)
                    if post_found:
                        post = page.locator(f'xpath=//div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[{post_crawled+1}][node() and not(@class)]')
                    else:
                        if last_post:
                            print("Last post reached")
                            break
                        else:
                            raise Exception(f"Unable to find post no.{post_crawled+1}")
                            
                # Get specific crawl zone in a post since html structure very complicated
                post_crawl_zone = post.locator('xpath=./div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div')
                if post_crawl_zone.count() == 0:
                    raise Exception(f"Unable to find post crawl zone for post {post_crawled+1}")
                else:
                    print(f"Found post no.{post_crawled+1}")

                # content container div tag (need to scroll)
                content_container = post_crawl_zone.locator('xpath=./div[3]/div/div/div/div/div/span/div')
                if content_container.count() == 0:
                    raise Exception(f"Unable to find content container for post {post_crawled+1}")

                # Handle "read more button"
                read_more_button = content_container.locator('xpath=.//div[contains(@role,"button")]')
                if read_more_button.count() > 0:
                    read_more_button.click()
                    page.wait_for_timeout(500)

                # Get content
                raw_task["Content"] = self.convert_to_markdown(content_container.inner_html())

                # Get time
                raw_task["Time"] = post_crawl_zone.locator('xpath=./div[2]/div/div[2]/div/div[2]/span/div/span[1]/span/span/div').inner_text()

                raw_tasks.append(raw_task)
                post_crawled+=1
                print(f"Successfully crawled post no.{post_crawled}")
            except Exception as e:
                print(f"Error when crawling post: {e}\nMoving on to next post")
                post_crawled += 1
                continue
                
        return raw_tasks

# /html/body/div[1]/div/div[1]/div/div[3]/div/div/div[1]/div[1]/div/div = //div[contains(@role,"main")]
# post = //div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[{post_crawled+1}][node() and not(@class)]
# crawl_zone = //div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[1]/div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div
# content_container = //div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[1]/div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div/div[3]/div/div/div/div/div/span/div
# time = //div[contains(@role,"main")]/div[2]/div/div[2]/div/div[2]/div[3]/div[1]/div/div/div/div/div/div/div/div/div/div/div/div/div[not(@aria-hidden) and contains(@class,"html-div")]/div/div/div[2]/div/div[2]/div/div[2]/span/div/span[1]/span/span/div