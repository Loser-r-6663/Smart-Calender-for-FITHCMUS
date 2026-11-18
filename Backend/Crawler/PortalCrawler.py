from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler
from dotenv import load_dotenv
import os


class PortalCrawler(PlaywrightCrawler):
    def __init__(self):
        self.history_file = None
        self.state_file = "Backend/Crawler/State/PortalState.json"
        self.login_url = "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fsinh-vien%2fket-qua-dkhp"
        self.home_url = "https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp"
    
    def check_state(self, cookies):
        if not cookies:
            return False, {"headless": False, "storage_state": None}
        
        auth_cookie = cookies.get(".DOTNETNUKE") or cookies.get("TwoFaTrustedDevice")
        if not auth_cookie:
            return False, {"headless": False, "storage_state": None}
        
        expires = auth_cookie.get("expires", -1)
        if expires != -1 and self.time_is_expired(expires):
            return False, {"headless": False, "storage_state": None}
            
        settings = {"headless": True, "storage_state": self.state_file}
        try:
            self.login(settings)
            return True, settings
        except ConnectionError:
            return False, {"headless": False, "storage_state": None}
    
    def login(self, settings):
        headless = settings.get("headless", False)
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        if page.url == self.login_url or "login" in page.url.lower():
            if headless:
                browser.close()
                raise ConnectionError("Portal login session expired.")

            # Fill in the login form and submit
            load_dotenv()
            username = os.getenv("PORTAL_USERNAME")
            password = os.getenv("PORTAL_PASSWORD")
            if (
                username
                and password
                and username not in {"your", "your_portal_username_here"}
                and password not in {"your", "your_portal_password_here"}
            ):
                try:
                    page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtUsername"]').fill(username)
                    page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtPassword"]').fill(password)
                    page.locator('xpath=//*[@id="dnn_ctr_Login_DNN"]/div/div[3]/span[2]/span/span').click()
                    page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_cmdLogin"]').click()
                except Exception:
                    pass
            else:
                print("ℹ️ Vui lòng đăng nhập tài khoản Portal trên cửa sổ trình duyệt đang mở...")
            
            # Manually enter the code from the email
            page.wait_for_url(self.home_url, timeout=120000) # 2 min
            
            context.storage_state(path=self.state_file)
        browser.close()
    
    def browse_page(self, page):
        page.wait_for_selector("table", timeout=15000)
        rows = page.locator("table tr").all()
        if not rows: return []
        
        # Extract headers and table data
        headers = rows[0].locator("th").all_inner_texts()
        table = [
            dict(zip(headers, row.locator("td").all_inner_texts()))
            for row in rows[1:] if row.locator("td").count() > 0
        ]
        
        # Process table data and create RawTask objects
        raw_tasks: list[RawTask] = []
        for row in table:
            title = f'{row["Mã MH"]} · {row["Tên MH"]}'
            course = row["Tên MH"]

            for col_name, desc in (("Lịch LT", "Lý Thuyết"), ("Lịch TH", "Thực Hành")):
                schedule_val = row.get(col_name)
                if not schedule_val:
                    continue

                text = str(schedule_val).strip()
                if "(" in text:
                    duration, location = text.rstrip(")").split(" (", 1)
                else:
                    duration, location = text, None

                if not location:
                    loc_str = "Cơ sở 1"
                elif any(k in location.lower() for k in ("cơ sở", "cs1", "cs2", "linh trung")):
                    loc_str = location
                else:
                    loc_str = f"{location}, Cơ sở 1"

                raw_tasks.append(
                    RawTask(
                        Title=title,
                        Type="class",
                        Course=course,
                        Description=desc,
                        Duration=duration,
                        Location=loc_str,
                        Link=self.home_url,
                    )
                )

        return raw_tasks
