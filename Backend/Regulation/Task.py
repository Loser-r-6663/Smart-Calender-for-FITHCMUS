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
    Title: str = "N/A"           # Title of the post
    Type: str = "N/A"            # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    Description: str = "N/A"     # Description or brief summary of the post
    CreateDate: str = "N/A"      # Creation date of the post
    Duration: str = "N/A"        # Duration of the task or event
    Deadline: str = "N/A"        # Assignment deadline
    Course: str = "N/A"          # Course associated with the post
    Location: str = "N/A"        # Location of the event or task
    Content: str = "N/A"         # Full content of the post
    Link: str = "N/A"            # Link to the original post
    Platform: str = "N/A"        # Platform from which the post was crawled (e.g., Portal, Facebook)


class ExtractedTask(BaseTask):
    title: str = Field(
        description="Tiêu đề chính xác, ngắn gọn và rõ ràng của nhiệm vụ, sự kiện hoặc thông báo"
    )
    type: Literal["assignment", "announcement", "event", "personal"] = Field(
        description="Phân loại bài viết (assignment: bài tập, announcement: thông báo chung, event: thông báo tổ chức sự kiện, personal: thông tin cá nhân)"
    )
    estimated_hours: float = Field(
        description="Ước tính số giờ cần thiết để tham gia hoặc hoàn thành (ví dụ: 2.0)"
    )
    course: str = Field(
        default=None,
        description="Tên môn học hoặc mã môn học liên quan (nếu đây là bài tập hoặc thông báo môn học)"
    )
    description: str | None = Field(
        default=None,
        description="Tóm tắt ngắn gọn 1-3 câu nội dung chính của thông báo"
    )
    target_audience: str | None = Field(
        default=None,
        description="Đối tượng áp dụng hoặc tham gia (ví dụ: 'Sinh viên năm 1', 'Sinh viên chương trình Đề án', 'Khoa CNTT')"
    )
    location: str | None = Field(
        default=None,
        description="Địa điểm diễn ra sự kiện (ví dụ: 'Hội trường I, cơ sở 1', 'Phòng C.32', 'Online qua MS Teams')"
    )
    registration_start: datetime | None = Field(
        default=None,
        description="Thời gian bắt đầu mở cổng đăng ký (định dạng ISO 8601)"
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
    source_url: str = Field(
        description="Đường link bài viết gốc hoặc link form đăng ký"
    )
    source_platform: Literal["Portal", "Moodle", "Facebook", "FIT", "HCMUS", "OSA"] = Field(
        description="Nền tảng nguồn"
    )
    updated_at: datetime = Field(
        description="Thời điểm trích xuất dữ liệu này"
    )
