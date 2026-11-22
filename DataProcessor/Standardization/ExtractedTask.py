from typing import Literal
from datetime import datetime
from pydantic import Field, model_validator

from DataProcessor.Standardization.BaseTask import BaseTask, TargetAudience, Location, DateDayTime
from DataProcessor.Standardization.RawTask import RawTask


class ExtractedTask(BaseTask):
    id: str | None = Field(
        default=None
    )
    user_id: str | None = Field(
        default=None,
        description="ID của người dùng nếu đây là task riêng (user_task)"
    )
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
        description="Đối tượng áp dụng hoặc tham gia gồm các key cố định: year (năm học/khóa), program (chương trình), faculty (khoa/ngành), other (đối tượng khác). Nếu không đề cập thì để None"
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
    start_time: DateDayTime | None = Field(
        default=None,
        description="Thời gian bắt đầu diễn ra sự kiện/buổi học, có thể là ngày giờ cụ thể hoặc là thứ và khung giờ (lặp lại hàng tuần)"
    )
    end_time: DateDayTime | None = Field(
        default=None,
        description="Thời gian kết thúc sự kiện/buổi học, có thể là ngày giờ cụ thể hoặc là thứ và khung giờ (lặp lại hàng tuần)"
    )
    deadline: datetime | None = Field(
        default=None,
        description="Hạn chót nộp bài tập hoặc hạn chót hoàn thành nhiệm vụ"
    )
    training_points: int | None = Field(
        default=None,
        description="Số điểm rèn luyện (ĐRL) sinh viên nhận được nếu tham gia (ví dụ: 5, 10). Nếu không đề cập thì để None"
    )
    training_point_category: Literal["Articles 1", "Articles 2", "Articles 3", "Articles 4", "Articles 5"] | None = Field(
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
    source_platform: Literal["Portal", "Moodle", "Khoa Công nghệ thông tin", "Trường đại học Khoa học tự nhiên", "Phòng Công tác sinh viên", "VNUHCMUS", "Đoàn trường Khoa học tự nhiên", "Đoàn khoa - Liên chi hội khoa Môi trường", "Đoàn khoa - Liên chi hội khoa Hóa học", "Đoàn khoa - Liên chi hội khoa Sinh học", "Đoàn khoa - Liên chi hội khoa Địa chất", "Đoàn khoa - Liên chi hội khoa Vật lý", "Facebook Khoa Công nghệ thông tin"] = Field(
        description="Nền tảng nguồn"
    )
    updated_at: datetime = Field(
        description="Thời điểm trích xuất dữ liệu này"
    )
    
    @model_validator(mode="after")
    def check_event_requires_training_points(self):
        if self.type == "event":
            if self.training_points is None or not (0 <= self.training_points <= 24):
                raise ValueError("training_points phải nằm trong khoảng 0-24 cho sự kiện.")
            if self.training_points > 0:
                if self.training_point_category is None:
                    raise ValueError("training_point_category bắt buộc phải có khi training_points > 0.")
            elif self.training_point_category is not None:
                raise ValueError("training_point_category phải là None khi training_points = 0.")
        return self
    
    @model_validator(mode="after")
    def check_event_requires_estimated_hours(self):
        if self.type == "event" and (self.estimated_hours is None or self.estimated_hours <= 0):
            raise ValueError("estimated_hours phải được cung cấp cho các nhiệm vụ khi type là 'event'.")
        return self
    
    @model_validator(mode="after")
    def check_assignment_estimated_hours(self):
        if self.type == "assignment" and self.estimated_hours is not None and self.estimated_hours <= 0:
            raise ValueError("Khi type là 'assignment'. Nếu thiếu thông tin để tính estimated_hours, chia thành 2 trường hợp, ngắn hạn thì estimated_hours = 1-4, dài hạn thì estimated_hours = None")
        return self
    
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
