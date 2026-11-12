from Backend.Crawler.FBCrawlerBase import FBCrawler

class FBCrawler_VNUHCMUS(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/VNUHCMUSHistory.txt",
            "https://www.facebook.com/VNUHCM.US"
        )

class FBCrawler_YUHCMUS(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUHCMUSHistory.txt",
            "https://www.facebook.com/DoanHoiHCMUS"
        )

class FBCrawler_YUE(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUEHistory.txt",
            "https://www.facebook.com/doanhoikhoamoitruong"
        )

class FBCrawler_YUC(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUCHistory.txt",
            "https://www.facebook.com/doankhoa.lienchihoi.hoahoc.khtn"
        )

class FBCrawler_YUB(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUBHistory.txt",
            "https://www.facebook.com/DoanKhoa.LienChiHoi.KhoaSinhHoc.DHKHTN"
        )

class FBCrawler_YUG(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUGHistory.txt",
            "https://www.facebook.com/dk.lch.diachatkhtn"
        )

class FBCrawler_YUP(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/YUPHistory.txt",
            "https://www.facebook.com/doanhoikhoavatly"
        )

class FBCrawler_FIT(FBCrawler):
    def __init__(self):
        super().__init__(
            "Backend/Crawler/History/FBFITHistory.txt",
            "https://www.facebook.com/fit.hcmus.hoatdong"
        )