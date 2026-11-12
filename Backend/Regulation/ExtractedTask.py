from pydantic import Field
from datetime import datetime
from typing import Literal

from Backend.Regulation.BaseTask import BaseTask, TargetAudience, Location, DayTime
from Backend.Regulation.RawTask import RawTask


class ExtractedTask(BaseTask):
    title: str = Field(
        description="Tiêu đề chính xác, ngắn gọn và rõ ràng của nhiệm vụ, sự kiện hoặc thông báo"
    )
    type: Literal["class", "assignment", "announcement", "event"] = Field(
        description="Phân loại bài viết (class: lịch học, assignment: bài tập, announcement: thông báo chung, event: thông báo tổ chức sự kiện)"
    )
    course: str | None = Field(
        default=None,
        description="Tên môn học hoặc mã môn học liên quan (nếu đây là bài tập hoặc thông báo môn học)"
    )
    description: str | None = Field(
        default=None,
        description="Tóm tắt ngắn gọn 1-3 câu nội dung chính của thông báo"
    )
    target_audience: TargetAudience | None = Field(
        default=None,
        description="Đối tượng áp dụng hoặc tham gia gồm các key cố định: year (năm học/khóa), program (chương trình), faculty (khoa/ngành), other (đối tượng khác)"
    )
    location: Location | None = Field(
        default=None,
        description="Địa điểm diễn ra sự kiện hoặc buổi học gồm các key cố định: room (phòng/hội trường/nền tảng online), campus (cơ sở), detail (chi tiết địa chỉ)"
    )
    registration_start: datetime | None = Field(
        default=None,
        description="Thời gian bắt đầu mở cổng đăng ký"
    )
    registration_end: datetime | None = Field(
        default=None,
        description="Thời gian đóng cổng đăng ký"
    )
    start_time: datetime | DayTime | None = Field(
        default=None,
        description="Thời gian bắt đầu diễn ra sự kiện/buổi học, có thể là ngày giờ cụ thể hoặc là thứ và khung giờ (lặp lại hàng tuần)"
    )
    end_time: datetime | DayTime | None = Field(
        default=None,
        description="Thời gian kết thúc sự kiện/buổi học, có thể là ngày giờ cụ thể hoặc là thứ và khung giờ (lặp lại hàng tuần)"
    )
    deadline: datetime | None = Field(
        default=None,
        description="Hạn chót nộp bài tập hoặc hạn chót hoàn thành nhiệm vụ"
    )
    training_points: int | None = Field(
        default=None,
        description="Số điểm rèn luyện (ĐRL) sinh viên nhận được nếu tham gia (ví dụ: 5, 10). Nếu không đề cập thì để null"
    )
    training_point_category: Literal["articles 1", "articles 2", "articles 3", "articles 4", "articles 5"] | None = Field(
        default=None,
        description="Điều hoặc mục cộng điểm rèn luyện nếu có (ví dụ: 'Điều 3', 'Mục 2.1')"
    )
    estimated_hours: float | None = Field(
        default=None,
        description="Ước tính số giờ cần thiết để tham gia hoặc hoàn thành (ví dụ: 2.0)"
    )
    source_url: str = Field(
        description="Đường link bài viết gốc hoặc link form đăng ký"
    )
    source_platform: Literal["Portal", "Moodle", "Khoa Công nghệ thôn tin", "Trường đại học Khoa học tự nhiên", "Phòng Công tác sinh viên", "VNUHMCUS", "Đoàn trường Khoa học tự nhiên", "Đoàn khoa - Liên chi hội khoa Môi trường", "Đoàn khoa - Liên chi hội khoa Hóa học", "Đoàn khoa - Liên chi hội khoa Sinh học", "Đoàn khoa - Liên chi hội khoa Địa chất", "Đoàn khoa - Liên chi hội khoa Vật lý", "Facebook Khoa Công nghệ thôn tin"] = Field(
        description="Nền tảng nguồn"
    )
    updated_at: datetime = Field(
        description="Thời điểm trích xuất dữ liệu này"
    )
    
    @classmethod
    def from_raw_task(cls, raw_task: RawTask) -> "ExtractedTask":
        """Create an ExtractedTask instance from a RawTask instance."""
        location_obj = None
        if raw_task.location:
            if isinstance(raw_task.location, Location):
                location_obj = raw_task.location
            elif isinstance(raw_task.location, dict):
                location_obj = Location(**raw_task.location)
            else:
                location_obj = Location(room=str(raw_task.location))
        
        return cls(
            title=raw_task.title or "",
            type=raw_task.type or "class",
            course=raw_task.course,
            description=raw_task.description,
            target_audience=None,
            location=location_obj,
            registration_start=None,
            registration_end=None,
            start_time=raw_task.start_time,
            end_time=raw_task.end_time,
            deadline=raw_task.deadline,
            training_points=None,
            training_point_category=None,
            estimated_hours=None,
            source_url=raw_task.link or "",
            source_platform=raw_task.platform or "Portal",
            updated_at=raw_task.updated_at or datetime.now()
        )
