from Backend.Crawler.BaseCrawler import PlaywrightCrawler, expect
import re


class OSACrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = None
        self.home_url = "https://ctsv.hcmus.edu.vn/info/"
    
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
                raw_task["Link"] = page.url

                content_element = page.locator('div.hcmus-content')
                expect(content_element).to_have_text(re.compile(r".+"))
                raw_task["Content"] = content_element.inner_text().strip()

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