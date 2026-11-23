from pydantic import BaseModel, Field, field_validator
from datetime import date as datetime_date, datetime, time as datetime_time
from typing import Literal

YEAR = datetime.now().year


class TargetAudience(BaseModel):
    year: Literal["1", "2", "3", "4"] | None = Field(
        default=None,
        description=f"Năm học áp dụng (năm 1 = khóa {YEAR}, năm 2 = khóa {YEAR-1}, năm 3 = khóa {YEAR-2}, năm 4 = khóa {YEAR-3}). Nếu không đề cập thì để None"
    )
    program: Literal["Đại trà (chuẩn)", "Đề án", "Tăng cường tiếng Anh (chất lượng cao)", "Tiên tiến / Liên kết quốc tế", "Cử nhân tài năng", "Đại học chính quy", "Sau đại học"] | None = Field(
        default=None,
        description="Chương trình đào tạo áp dụng. Nếu không đề cập thì để None"
    )
    faculty: Literal["Toán - Tin học", "Công nghệ Thông tin", "Vật lý - Vật lý Kỹ thuật", "Hóa học", "Sinh học - Công nghệ Sinh học", "Điện tử - Viễn thông", "Khoa học và Công nghệ Vật liệu", "Môi trường", "Địa chất", "Khoa học Liên ngành"] | None = Field(
        default=None,
        description="Khoa hoặc chuyên ngành áp dụng. Nếu không đề cập thì để None"
    )
    other: str | None = Field(
        default=None,
        description="Tiêu chí hoặc đối tượng áp dụng bổ sung khác nếu có (ví dụ: 'Toàn trường', 'Nữ sinh', 'Cán bộ Đoàn - Hội')"
    )


class Location(BaseModel):
    room: str | Literal["Online"] | None = Field(
        default=None,
        description="Phòng học, hội trường hoặc nền tảng trực tuyến (ví dụ: 'C.32', 'Giảng đường 1', 'Hội trường I', 'Online')"
    )
    campus: Literal["Nguyễn Văn Cừ (cơ sở 1)", "Thủ Đức (cơ sở 2)"] | None = Field(
        default=None,
        description="Cơ sở tổ chức"
    )
    detail: str | None = Field(
        default=None,
        description="Địa chỉ chi tiết hoặc thông tin bổ sung về địa điểm (ví dụ: '227 Nguyễn Văn Cừ, Phường 4, Quận 5', 'Tòa nhà F')"
    )


class DateDayTime(BaseModel):
    date: datetime_date | None = Field(
        default=None,
        description="Ngày cụ thể (ví dụ: '2026-11-22')"
    )
    day: Literal["T2", "T3", "T4", "T5", "T6", "T7", "CN"] | None = Field(
        default=None,
        description="Thứ trong tuần lặp lại hàng tuần"
    )
    time: datetime_time | None = Field(
        default=None,
        description="Giờ trong ngày không chứa ngày (ví dụ: '08:00:00')"
    )
    
    @field_validator("time", mode="after")
    @classmethod
    def strip_time_tz(cls, v: datetime_time | None):
        if v is not None and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        return v
    
    def __eq__(self, other):
        if not isinstance(other, DateDayTime):
            return NotImplemented
        
        def _is_time_equal(t1: datetime_time | None, t2: datetime_time | None):
            if None in (t1, t2):
                return True
            return t1.replace(tzinfo=None) == t2.replace(tzinfo=None)

        return (
            (self.date == other.date or None in (self.date, other.date))
            and (self.day == other.day or None in (self.day, other.day))
            and _is_time_equal(self.time, other.time)
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
                tz = f" {v:%z}" if v.tzinfo else ""
                return f"'{v:%Y-%m-%d %H:%M:%S}{tz}'"
            if isinstance(v, datetime_time):
                return f"'{v:%H:%M:%S}'"
            if isinstance(v, DateDayTime):
                if v.date is not None:
                    date_text = v.date.isoformat()
                    return f"'{date_text} {v.time:%H:%M:%S}'" if v.time is not None else f"'{date_text}'"
                return f"'{v.day} {v.time:%H:%M:%S}'" if v.time is not None else repr(v.model_dump(mode="json"))
            if isinstance(v, BaseModel):
                return repr(v.model_dump(mode="json"))
            return repr(v)
        
        fields = "\n".join(f"\t{k}: {format_value(v)}" for k, v in self)
        return f"\n{self.__class__.__name__}(\n{fields}\n)"
    
    __str__ = __repr__
