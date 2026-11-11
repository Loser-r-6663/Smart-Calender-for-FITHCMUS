from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class BaseTask(BaseModel):
    def update(self, **kwargs):
        """Update the attributes of the RawTask instance with the provided keyword arguments."""
        for key, value in kwargs.items():
            if key in self.model_fields: setattr(self, key, value)
        return self
    
    def __repr__(self):
        def format_value(v):
            if isinstance(v, datetime):
                return f"'{v:%Y-%m-%d %H:%M:%S}'"
            return repr(v)
        
        fields = "\n".join(f"\t{k}: {format_value(v)}" for k, v in self)
        return f"\n{self.__class__.__name__}(\n{fields}\n)"
    
    __str__ = __repr__


class RawTask(BaseTask):
    title: str | None = None            # Title of the post
    type: str | None = None             # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    description: str | None = None      # Description or brief summary of the post
    create_date: str | None = None      # Creation date of the post
    duration: str | None = None         # Duration of the task or event
    deadline: datetime | None = None    # Assignment deadline
    course: str | None = None           # Course associated with the post
    location: str | None = None         # Location of the event or task
    content: str | None = None          # Full content of the post
    link: str | None = None             # Link to the original post
    platform: str | None = None         # Platform from which the post was crawled
    updated_at: datetime | None = None  # Timestamp of when the data was extracted


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
    target_audience: str | None = Field(
        default=None,
        description="Đối tượng áp dụng hoặc tham gia có dạng: năm học, chương trình, khoa (ví dụ: 'năm 1, chương trình Đề án, khoa CNTT')"
    )
    location: str | None = Field(
        default=None,
        description="Địa điểm diễn ra sự kiện có dạng: phòng, cơ sở (ví dụ: 'giảng đường 1, cơ sở Nguyễn Văn Cừ', 'C.32, cơ sở 2')"
    )
    registration_start: datetime | None = Field(
        default=None,
        description="Thời gian bắt đầu mở cổng đăng ký"
    )
    registration_end: datetime | None = Field(
        default=None,
        description="Thời gian đóng cổng đăng ký"
    )
    start_time: datetime | None = Field(
        default=None,
        description="Thời gian bắt đầu diễn ra sự kiện/buổi học"
    )
    end_time: datetime | None = Field(
        default=None,
        description="Thời gian kết thúc sự kiện/buổi học"
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
    duration: str | None = Field(
        default=None,
        description="Thời lượng diễn ra sự kiện hoặc buổi học lặp lại hàng tuần (ví dụ: T4 14:00-16:00, T6 08:00-10:00)"
    )
    source_url: str = Field(
        description="Đường link bài viết gốc hoặc link form đăng ký"
    )
    source_platform: Literal["Portal", "Moodle", "Facebook", "FIT", "HCMUS", "OSA"] = Field(
        description="Nền tảng nguồn"
    )
    updated_at: datetime = Field(
        description="Thời điểm trích xuất dữ liệu này"
    )
    
    def from_raw_task(raw_task: RawTask) -> "ExtractedTask":
        """Create an ExtractedTask instance from a RawTask instance."""
        return ExtractedTask(
            title=raw_task.title or "",
            type=raw_task.type or "class",
            course=raw_task.course,
            description=raw_task.description,
            target_audience=None,
            location=raw_task.location,
            registration_start=None,
            registration_end=None,
            start_time=None,
            end_time=None,
            deadline=raw_task.deadline,
            training_points=None,
            training_point_category=None,
            duration=raw_task.duration,
            source_url=raw_task.link or "",
            source_platform=raw_task.platform or "Portal",
            updated_at=raw_task.updated_at or datetime.now()
        )
