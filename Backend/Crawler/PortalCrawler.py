import os
from datetime import datetime

from Backend.Crawler.BaseCrawler.BaseCrawler import RawTask
from Backend.Regulation.ExtractedTask import Location, DayTime
from Backend.Regulation.User import User
from Backend.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler


get_location = lambda v: Location(room=v, campus="Nguyễn Văn Cừ (cơ sở 1)") if v else None
def get_daytime(v: str):
    if not v: return (None, None)
    day, time_range = v.split(" ")
    start_time, end_time = time_range.split("-")
    
    start_time = datetime.strptime(start_time, "%H:%M").time()
    end_time = datetime.strptime(end_time, "%H:%M").time()
    
    return DayTime(day=day, time_=start_time), DayTime(day=day, time_=end_time)


class PortalCrawler(PlaywrightCrawler):
    def __init__(self, user: User):
        self.history_file = None
        
        if user.portal_session:
            self.state_file = "Backend/Crawler/State/PortalState.json"
            with open(self.state_file, "w") as f:
                f.write(user.portal_session)
        else: self.state_file = None
        
        self.login_url = "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fsinh-vien%2fket-qua-dkhp"
        self.home_url = "https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp"
        self.user = user
    
    def check_state(self, cookies):
        assert self.user.portal_username and self.user.portal_password
        assert self.user.portal_session
        
        if not cookies:
            assert os.environ.get("APP_ROLE") != "SERVER"
            return False, {"headless": False, "storage_state": None}
        
        if self.time_is_expired(cookies["TwoFaTrustedDevice"]["expires"]):
            assert os.environ.get("APP_ROLE") != "SERVER"
            return False, {"headless": False, "storage_state": None}
        else:
            return False, {"headless": True, "storage_state": self.state_file}
    
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
            page.wait_for_url(self.home_url, timeout=120000) # 2 min
            
            context.storage_state(path=self.state_file)
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
        
        return [task.update(Platform="Portal") for task in raw_tasks]
