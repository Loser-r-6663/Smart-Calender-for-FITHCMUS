from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class UserTaskPreference(BaseModel):
    """Pydantic model đại diện cho tùy chỉnh và kết quả xếp lịch của user trên bảng 'user_task_preferences'."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str | None = Field(
        default=None,
        description="ID người dùng trong hệ thống (UUID)"
    )
    task_id: str = Field(
        description="ID của task/sự kiện trong bảng tasks hoặc user_task"
    )
    pin_status: Literal["default", "pinned", "rejected"] = Field(
        default="default",
        description="Trạng thái ghim hoặc loại bỏ sự kiện do user chọn"
    )
    custom_start_time: datetime | str | None = Field(
        default=None,
        alias="custom_start_at",
        description="Thời gian bắt đầu tùy chỉnh khi user Reschedule"
    )
    custom_end_time: datetime | str | None = Field(
        default=None,
        alias="custom_end_at",
        description="Thời gian kết thúc tùy chỉnh khi user Reschedule"
    )
    travel_buffer_minutes: int | dict[str, int] | None = Field(
        default=None,
        description="Thời gian di chuyển ước tính (phút): 1 số chung hoặc {'cs1': x, 'cs2': y}"
    )
    is_scheduled: bool = Field(
        default=False,
        description="Sự kiện có đang nằm trong lịch tối ưu hiện tại của user hay không"
    )
    scheduled_start_time: datetime | str | None = Field(
        default=None,
        alias="scheduled_start_at",
        description="Thời gian bắt đầu cụ thể do Scheduler xếp"
    )
    scheduled_end_time: datetime | str | None = Field(
        default=None,
        alias="scheduled_end_at",
        description="Thời gian kết thúc cụ thể do Scheduler xếp"
    )
    points_gained: int | None = Field(
        default=None,
        description="Số điểm ĐRL thực nhận của sự kiện trong lịch hiện tại"
    )
    updated_at: datetime | str | None = Field(
        default=None,
        description="Thời điểm cập nhật gần nhất"
    )
