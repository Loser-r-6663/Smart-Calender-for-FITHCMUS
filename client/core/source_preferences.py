from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CrawlerSource:
    name: str
    detail: str
    url: str


SOURCE_GROUPS: tuple[tuple[str, tuple[CrawlerSource, ...]], ...] = (
    (
        "Personal accounts",
        (
            CrawlerSource(
                "Portal",
                "Classes and registered courses",
                "https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp",
            ),
            CrawlerSource(
                "Moodle",
                "Assignments and course deadlines",
                "https://courses.ctda.hcmus.edu.vn/my/",
            ),
        ),
    ),
    (
        "University websites",
        (
            CrawlerSource(
                "Khoa Công nghệ thông tin",
                "Faculty website",
                "https://www.ctda.hcmus.edu.vn/vi/thong-bao/",
            ),
            CrawlerSource(
                "Trường đại học Khoa học tự nhiên",
                "University website",
                "https://hcmus.edu.vn/category/dao-tao/dai-hoc/thong-tin-danh-cho-sinh-vien/",
            ),
            CrawlerSource(
                "Phòng Công tác sinh viên",
                "Student affairs website",
                "https://ctsv.hcmus.edu.vn/news",
            ),
        ),
    ),
    (
        "Official social pages",
        (
            CrawlerSource(
                "VNUHCMUS",
                "University Facebook page",
                "https://www.facebook.com/VNUHCM.US",
            ),
            CrawlerSource(
                "Đoàn trường Khoa học tự nhiên",
                "University Youth Union",
                "https://www.facebook.com/DoanHoiHCMUS",
            ),
            CrawlerSource(
                "Đoàn khoa - Liên chi hội khoa Môi trường",
                "Environment student union",
                "https://www.facebook.com/doanhoikhoamoitruong",
            ),
            CrawlerSource(
                "Đoàn khoa - Liên chi hội khoa Hóa học",
                "Chemistry student union",
                "https://www.facebook.com/doankhoa.lienchihoi.hoahoc.khtn",
            ),
            CrawlerSource(
                "Đoàn khoa - Liên chi hội khoa Sinh học",
                "Biology student union",
                "https://www.facebook.com/DoanKhoa.LienChiHoi.KhoaSinhHoc.DHKHTN",
            ),
            CrawlerSource(
                "Đoàn khoa - Liên chi hội khoa Địa chất",
                "Geology student union",
                "https://www.facebook.com/dk.lch.diachatkhtn",
            ),
            CrawlerSource(
                "Đoàn khoa - Liên chi hội khoa Vật lý",
                "Physics student union",
                "https://www.facebook.com/doanhoikhoavatly",
            ),
            CrawlerSource(
                "Facebook Khoa Công nghệ thông tin",
                "Faculty Facebook page",
                "https://www.facebook.com/fit.hcmus.hoatdong",
            ),
        ),
    ),
)

ALL_SOURCE_NAMES = frozenset(
    source.name for _, sources in SOURCE_GROUPS for source in sources
)
