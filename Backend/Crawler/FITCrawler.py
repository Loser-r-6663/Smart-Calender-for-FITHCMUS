from Backend.Crawler.BaseCrawler import BeautifulSoupCrawler


class FITCrawler(BeautifulSoupCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/FITState.txt"
        self.login_url = "https://courses.ctda.hcmus.edu.vn/my/"
        self.home_url = "https://courses.ctda.hcmus.edu.vn/my/"
    
    def parse(self, soup):
        return
