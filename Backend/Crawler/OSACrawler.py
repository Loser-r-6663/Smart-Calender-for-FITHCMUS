from Backend.Crawler.BaseCrawler import PlaywrightCrawler
from playwright.sync_api import sync_playwright

class OSACrawler(PlaywrightCrawler):

    def __init__(self):
        self.state_file = "Backend/Crawler/State/OSAState.json"
        self.home_url = "https://ctsv.hcmus.edu.vn/info/"

    def login(self, p, state_file):
        # Login
        storage_state = None if state_file["NotFound"] else self.state_file
        browser = p.chromium.launch(headless=not (state_file["NotFound"] or state_file["AllExpires"]))
        context = browser.new_context(storage_state=storage_state)

        page = context.new_page()
        page.goto(self.home_url)

        context.storage_state(path=self.state_file)
        browser.close()

    def interact(self, page):
        # Access homepage, wait for loading
        page.goto(self.home_url, wait_until="networkidle")
        try:
            page.wait_for_selector('xpath=//div[contains(@class, "cursor-pointer") and contains(@class, "h-full")]', timeout=10000)
        except Exception as e:
            print(f"Timeout waiting for posts to load: {e}")
            return []
        
        # Get all articles
        article_elements = page.locator('xpath=//div[contains(@class, "cursor-pointer") and contains(@class, "h-full")]')
        count = article_elements.count()
        print(f"Found {count} posts using XPath.")

        # Initialize raw tasks
        raw_tasks = []
        for i in range(count):
            raw_task = {
                "Title": "N/A",
                "Link": "N/A",
                "Type": "N/A",
                "Date": "N/A",
                "Content": "N/A",
            }

            try:
                # Set article
                article = article_elements.nth(i)

                # Get title
                title_element = article.locator('xpath=.//div[contains(@class,"p-5 flex")]//h3/span[1]')
                if title_element.count() > 0:
                    raw_task["Title"] = title_element.inner_text().strip()

                # Get type of activity
                type_element = article.locator('xpath=.//div[contains(@class, "top-3") and contains(@class, "left-3")]')
                if type_element.count() > 0:
                    raw_task["Type"] = type_element.inner_text().strip()

                # Get post date
                date_element = article.locator('xpath=.//div[contains(@class,"p-5 flex")]//h3/span[2]/span')
                if date_element.count() > 0:
                    raw_task["Date"] = date_element.inner_text().strip()

                # Get link and content
                article.click()
                page.wait_for_load_state("networkidle")

                raw_task["Link"] = page.url

                content_element = page.locator('xpath=//div[contains(@class,"hcmus-content")]')
                if content_element.count() > 0:
                    raw_task["Content"] = content_element.first.inner_text().strip()

                # Add to results
                raw_tasks.append(raw_task)

                # Go back to homepage, wait for loading
                page.go_back()
                page.wait_for_selector('xpath=//div[contains(@class, "cursor-pointer") and contains(@class, "h-full")]', timeout=10000)

            except Exception as e:
                print(f"Error when parsing an article item with XPath: {e}")
                try:
                    page.goto(self.home_url, wait_until="networkidle")
                    page.wait_for_selector('xpath=//div[contains(@class, "cursor-pointer") and contains(@class, "h-full")]', timeout=10000)
                except:
                    pass
                continue

        return raw_tasks