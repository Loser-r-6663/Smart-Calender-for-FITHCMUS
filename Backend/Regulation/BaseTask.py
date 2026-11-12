from pydantic import BaseModel, Field
from datetime import datetime, time
from typing import Literal


class TargetAudience(BaseModel):
    year: str | None = Field(
        default=None,
        description="Năm học hoặc khóa sinh viên áp dụng (ví dụ: 'năm 1', 'khóa 2023', 'tất cả')"
    )
    program: str | None = Field(
        default=None,
        description="Chương trình đào tạo áp dụng (ví dụ: 'Chuẩn', 'Chất lượng cao', 'Đề án', 'Tiên tiến', 'tất cả')"
    )
    faculty: str | None = Field(
        default=None,
        description="Khoa hoặc chuyên ngành áp dụng (ví dụ: 'Công nghệ thông tin', 'Toán - Tin', 'Hóa học', 'tất cả')"
    )
    other: str | None = Field(
        default=None,
        description="Tiêu chí hoặc đối tượng áp dụng bổ sung khác nếu có (ví dụ: 'Toàn trường', 'Nữ sinh', 'Cán bộ Đoàn - Hội')"
    )


class Location(BaseModel):
    room: str | None = Field(
        default=None,
        description="Phòng học, hội trường hoặc liên kết/nền tảng trực tuyến (ví dụ: 'C.32', 'Giảng đường 1', 'Hội trường I', 'Google Meet', 'MS Teams')"
    )
    campus: str | None = Field(
        default=None,
        description="Cơ sở tổ chức (ví dụ: 'Nguyễn Văn Cừ', 'Thủ Đức', 'Online', '1', '2')"
    )
    detail: str | None = Field(
        default=None,
        description="Địa chỉ chi tiết hoặc thông tin bổ sung về địa điểm (ví dụ: '227 Nguyễn Văn Cừ, Phường 4, Quận 5', 'Tòa nhà F')"
    )


class DayTime(BaseModel):
    day: Literal["T2", "T3", "T4", "T5", "T6", "T7", "CN"] | None = Field(
        default=None,
        description="Thứ trong tuần (ví dụ: 'T2' cho Thứ Hai, 'T3' cho Thứ Ba, ..., 'CN' cho Chủ Nhật)"
    )
    time_: time = Field(
        default=None,
        description="Giờ trong ngày (không chứa ngày, ví dụ: '08:00:00')"
    )


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
            if isinstance(v, time):
                return f"'{v:%H:%M:%S}'"
            if isinstance(v, DayTime):
                return f"'{v.day} {v.time_:%H:%M:%S}'"
            if isinstance(v, BaseModel):
                return repr(v.model_dump(mode="json"))
            return repr(v)
        
        fields = "\n".join(f"\t{k}: {format_value(v)}" for k, v in self)
        return f"\n{self.__class__.__name__}(\n{fields}\n)"
    
    __str__ = __repr__
