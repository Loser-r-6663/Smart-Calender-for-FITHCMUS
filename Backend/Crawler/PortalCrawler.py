from Backend.Crawler.BaseCrawler import PlaywrightCrawler, time_is_expired
from dotenv import load_dotenv
import os


class PortalCrawler(PlaywrightCrawler):
    def __init__(self):
        self.state_file = "Backend/Crawler/State/PortalState.json"
        self.login_url = "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fsinh-vien%2fket-qua-dkhp"
        self.home_url = "https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp"
    
    def check_state(self, p, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}
        
        if time_is_expired(cookies["TwoFaTrustedDevice"]["expires"]):
            return False, {"headless": False, "storage_state": None}
        else:
            return False, {"headless": True, "storage_state": self.state_file}
    
    def login(self, p, browser_settings):
        browser, context, page = self.start_browser(p, browser_settings)
        page.goto(self.home_url)
        
        if page.url == self.login_url:
            # Fill in the login form and submit
            load_dotenv()
            username = os.getenv("PORTAL_USERNAME")
            password = os.getenv("PORTAL_PASSWORD")
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtUsername"]').fill(username)
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtPassword"]').fill(password)
            page.locator('xpath=//*[@id="dnn_ctr_Login_DNN"]/div/div[3]/span[2]/span/span').click()
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_cmdLogin"]').click()
            
            # Manually enter the code from the email
            page.wait_for_url(self.home_url, timeout=120000) # 2 min
            
            context.storage_state(path=self.state_file)
        browser.close()
    
    def interact(self, page):
        page.goto(self.home_url)
        
        table_selector = "table"
        page.wait_for_selector(table_selector, timeout=10000)
        
        return page.evaluate("""
            (selector) => {
                const table = document.querySelector(selector);
                if (!table) return [];
                
                // Get all rows
                const rows = Array.from(table.querySelectorAll('tr'));
                if (rows.length === 0) return [];
                
                // Extract headers from 'th' or fallback to default column names
                const firstRow = rows[0];
                const ths = firstRow.querySelectorAll('th');
                
                let headers, dataRows;
                if (ths.length > 0) {
                    headers = Array.from(ths).map(th => th.innerText.trim().replace(/\\s+/g, '_'));
                    dataRows = rows.slice(1); // Skip header row
                } else {
                    const tds = firstRow.querySelectorAll('td');
                    headers = Array.from({length: tds.length}, (_, i) => `Col_${i}`);
                    dataRows = rows; // Keep all rows
                }
                
                // Map rows to objects using headers as keys
                return dataRows.map(row => {
                    const tds = Array.from(row.querySelectorAll('td'));
                    let obj = {};
                    tds.forEach((td, i) => {
                        obj[headers[i] || `Col_${i}`] = td.innerText.trim();
                    });
                    return obj;
                }).filter(obj => Object.keys(obj).length > 0); // Remove empty rows
            }
        """, table_selector)
