from Backend.Crawler.BaseCrawler.BaseCrawler import BaseCrawler
from bs4 import BeautifulSoup
from http.client import HTTPResponse
from urllib.request import Request, urlopen


class BeautifulSoupCrawler(BaseCrawler):
    def launch_engine(self, url):
        request = Request(url, headers={"User-Agent": "UniversityLifeAssistant/1.0"})
        response: HTTPResponse = urlopen(request, timeout=30)
        html = response.read().decode(response.headers.get_content_charset() or "utf-8")
        response.close()
        
        page = BeautifulSoup(html, "html.parser")
        return page
    
    def browse_page(self, page: BeautifulSoup):
        """Extract and return the required data from the parsed document."""
