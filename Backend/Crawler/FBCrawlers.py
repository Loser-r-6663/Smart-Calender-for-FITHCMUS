from Backend.Crawler.FBCrawlerBase import FBCrawler


class FBCrawler_VNUHCMUS(FBCrawler):
    def __init__(self):
        super().__init__(
            "VNUHCMUSHistory",
            "https://www.facebook.com/VNUHCM.US"
        )

class FBCrawler_YUHCMUS(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUHCMUSHistory",
            "https://www.facebook.com/DoanHoiHCMUS"
        )

class FBCrawler_YUE(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUEHistory",
            "https://www.facebook.com/doanhoikhoamoitruong"
        )

class FBCrawler_YUC(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUCHistory",
            "https://www.facebook.com/doankhoa.lienchihoi.hoahoc.khtn"
        )

class FBCrawler_YUB(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUBHistory",
            "https://www.facebook.com/DoanKhoa.LienChiHoi.KhoaSinhHoc.DHKHTN"
        )

class FBCrawler_YUG(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUGHistory",
            "https://www.facebook.com/dk.lch.diachatkhtn"
        )

class FBCrawler_YUP(FBCrawler):
    def __init__(self):
        super().__init__(
            "YUPHistory",
            "https://www.facebook.com/doanhoikhoavatly"
        )

class FBCrawler_FIT(FBCrawler):
    def __init__(self):
        super().__init__(
            "FBFITHistory",
            "https://www.facebook.com/fit.hcmus.hoatdong"
        )