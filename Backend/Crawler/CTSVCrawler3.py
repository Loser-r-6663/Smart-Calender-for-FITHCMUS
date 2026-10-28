from Backend.Crawler.BaseCrawler import BeautifulSoupCrawler

class CTSVCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/CTSVState.txt"
        self.home_url = "https://ctsv.hcmus.edu.vn/info/"

    def parse(self, soup, last_post):
        raw_tasks = []
        articles = soup.select("div.cursor-pointer.h-full")
        print(len(articles))

        for article in articles:

            raw_task = {
                "Title": "N/A",
                "Link": "N/A",
                "Type": "N/A",
                "Date": "N/A",
                "Author": "N/A",
                "Content": "N/A"
            }

            try:
                upper_half = article.select_one('div.bg-white > div.relative')
                if upper_half == None:
                    print("Unable to find upper half of a post")
                bottom_half = article.select_one('div.bg-white > div.p-5"]')
                if upper_half == None:
                    print("Unable to find bottom half of a post")

                title_element = bottom_half.select_one('h3 span')
                raw_task["Title"] = title_element.get_text(strip=True)

                link_element = "N/A"
                all_a_tags = article.select('a')
                for a in all_a_tags:
                    href = a.get("href")
                    if href and "news" in href:  # Đang cố tìm thẻ a trong trang
                        print(href)

                type_element = upper_half.select_one('div.top-3.left-3')
                raw_task["Type"] = type_element.get_text(strip=True)

                date_element = upper_half.select_one(r'div.bottom-0.left-0 div.gap-1\.5')
                raw_task["Date"] = date_element.get_text(strip=True)

                raw_tasks.append(raw_task)

            except Exception as e:
                print(f"Error when parsing article item on CTSV news homepage: {e}")

        return raw_tasks