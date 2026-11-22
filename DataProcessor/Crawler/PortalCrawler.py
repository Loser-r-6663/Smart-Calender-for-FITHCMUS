import os
import json
from datetime import datetime

from DataProcessor.Standardization.User import User
from DataProcessor.Standardization.BaseTask import Location, DateDayTime
from DataProcessor.Crawler.BaseCrawler.BaseCrawler import RawTask
from DataProcessor.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler

APP_ROLE = os.environ.get("APP_ROLE")

get_location = lambda v: Location(room=v, campus="Nguyễn Văn Cừ (cơ sở 1)") if v else None
def get_daytime(v: str):
    if not v: return (None, None)
    day, time_range = v.split(" ")
    start_time, end_time = time_range.split("-")
    
    start_time = datetime.strptime(start_time, "%H:%M").time()
    end_time = datetime.strptime(end_time, "%H:%M").time()
    
    return DateDayTime(day=day, time=start_time), DateDayTime(day=day, time=end_time)


class PortalCrawler(PlaywrightCrawler):
    def __init__(self, user: User):
        self.history_key = None
        self.state_key = "PortalState"
        
        self.login_url = "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fsinh-vien%2fket-qua-dkhp"
        self.home_url = "https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp"
        self.user = user
    
    def get_state(self):
        if self.user.portal_session:
            return json.loads(self.user.portal_session)
    
    def check_state(self):
        assert self.user.portal_username and self.user.portal_password
        
        if not self.state:
            assert APP_ROLE != "SERVER"
            return False, {"headless": False, "storage_state": None}
        
        headless = APP_ROLE == "SERVER"
        return False, {"headless": headless, "storage_state": self.state}
    
    def login(self, settings):
        page, context, browser = self.launch_engine(self.home_url, settings)
        
        if page.url == self.login_url:
            # Fill in the login form and submit
            username = self.user.portal_username
            password = self.user.portal_password
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtUsername"]').fill(username)
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_txtPassword"]').fill(password)
            page.locator('xpath=//*[@id="dnn_ctr_Login_DNN"]/div/div[3]/span[2]/span/span').click()
            page.locator('xpath=//*[@id="dnn_ctr_Login_Login_DNN_cmdLogin"]').click()
            
            # Manually enter the code from the email
            if APP_ROLE != "SERVER":
                page.wait_for_url(self.home_url, timeout=120000) # 2 min
            else:
                try: page.wait_for_url(self.home_url)
                except: raise AssertionError("Please log in to Portal manually.")
        
            if APP_ROLE == "SERVER":
                self.state.update(context.storage_state())
            else:
                state_file = f"DataProcessor/Crawler/State/{self.state_key}.json"
                self.state.update(context.storage_state(path=state_file))
        browser.close()
    
    def browse_page(self, page):
        page.wait_for_selector("table", timeout=10000)
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
            
            dur_loc = lambda st: str(st).rstrip(")").split(" (") if "(" in st else (st or None, None)
            duration, location = dur_loc(row["Lịch LT"]); time_range = get_daytime(duration)
            raw_task = RawTask(
                title=title,
                type="class",
                description="Lý Thuyết" if row["Lịch LT"] else None,
                start_time=time_range[0],
                end_time=time_range[1],
                course=course,
                location=get_location(location),
                link=self.home_url
            )
            raw_tasks.append(raw_task)
            
            if row["Lịch TH"]:
                duration, location = dur_loc(row["Lịch TH"]); time_range = get_daytime(duration)
                raw_task = RawTask(
                    title=title,
                    type="class",
                    description="Thực Hành",
                    start_time=time_range[0],
                    end_time=time_range[1],
                    course=course,
                    location=get_location(location),
                    link=self.home_url
                )
                raw_tasks.append(raw_task)
        
        return raw_tasks
