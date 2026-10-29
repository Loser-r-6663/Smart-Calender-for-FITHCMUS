"""
Task Entity Model for Smart Virtual Assistant (FIT - HCMUS).
Implements the 22-field unified schema for representing all student activities:
- Class (Lịch học TKB)
- Assignment (Bài tập Moodle / Lab)
- Exam (Lịch thi giữa kỳ / cuối kỳ)
- Event (Sự kiện phong trào / Hội thảo ĐRL)
- Personal (Lịch hẹn cá nhân / Giờ ngủ / Việc đột xuất)
- Tuition (Thông báo hạn nộp học phí)
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# 1. CÁC ENUM ĐỊNH NGHĨA PHÂN LOẠI & TRẠNG THÁI
# =============================================================================

class TaskType(str, Enum):
    """Phân loại hình thái hoạt động sinh viên."""
    CLASS = "class"            # Lịch học TKB trên lớp
    ASSIGNMENT = "assignment"  # Bài tập về nhà, đồ án, nộp bài Moodle
    EXAM = "exam"              # Lịch thi, kiểm tra giữa kỳ / cuối kỳ
    EVENT = "event"            # Sự kiện, hội thảo, phong trào cộng ĐRL
    PERSONAL = "personal"      # Việc cá nhân (khám bệnh, làm thêm, hẹn bạn, ngủ)
    TUITION = "tuition"        # Thông báo hạn nộp học phí


class TaskStatus(str, Enum):
    """Trạng thái vòng đời của tác vụ."""
    ACTIVE = "active"          # Đang cần thực hiện
    DONE = "done"              # Đã hoàn thành / Đã nộp bài
    ARCHIVED = "archived"      # Đã hết hạn hoặc lưu trữ
    CANCELLED = "cancelled"    # Bị hủy bỏ


class DRLCategory(str, Enum):
    """5 Tiêu chí đánh giá Điểm Rèn Luyện theo Quy chế chính thức của ĐHKHTN - ĐHQG-HCM."""
    DIEU_1 = "dieu_1"  # Tham gia học tập và nghiên cứu khoa học (Tối đa: 30 điểm)
    DIEU_2 = "dieu_2"  # Chấp hành nội quy, quy chế và các quy định (Tối đa: 20 điểm)
    DIEU_3 = "dieu_3"  # Hoạt động CT-XH, VH-VN, TD-TT; phòng chống tội phạm, tệ nạn (Tối đa: 25 điểm)
    DIEU_4 = "dieu_4"  # Hành động hướng đến xây dựng và phát triển cộng đồng (Tối đa: 25 điểm)
    DIEU_5 = "dieu_5"  # Các nội dung khuyến khích (Tối đa: 30 điểm)


class SourcePlatform(str, Enum):
    """Nguồn thu thập dữ liệu."""
    MOODLE = "moodle"
    PORTAL = "portal"
    FACEBOOK = "facebook"
    CUSTOM = "custom"


# =============================================================================
# 2. HẰNG SỐ QUY CHẾ ĐIỂM RÈN LUYỆN (HCMUS DRL CAPS & INFO)
# =============================================================================

# Bảng tra cứu trần điểm tối đa từng tiêu chí theo Quy chế ĐRL HCMUS (Dùng trực tiếp cho CP-SAT)
DRL_CATEGORY_CAPS: dict[str, int] = {
    DRLCategory.DIEU_1.value: 30,  # 1. Học tập & NCKH
    DRLCategory.DIEU_2.value: 20,  # 2. Chấp hành nội quy, quy chế
    DRLCategory.DIEU_3.value: 25,  # 3. Chính trị - xã hội, văn thể mỹ
    DRLCategory.DIEU_4.value: 25,  # 4. Xây dựng và phát triển cộng đồng
    DRLCategory.DIEU_5.value: 30,  # 5. Các nội dung khuyến khích
}

# Thông tin chi tiết nội dung từng tiêu chí theo Quy chế phục vụ UI và RAG
DRL_CATEGORY_INFO: dict[str, dict[str, Any]] = {
    DRLCategory.DIEU_1.value: {
        "name": "Tham gia học tập và nghiên cứu khoa học",
        "max_score": 30,
        "criteria": [
            "Chấp hành các quy định liên quan đến học vụ và khảo thí",
            "Có kết quả học tập tốt và tiến bộ trong mỗi học kỳ",
            "Tích cực tham gia NCKH và các hoạt động học thuật",
        ],
    },
    DRLCategory.DIEU_2.value: {
        "name": "Chấp hành nội quy, quy chế và các quy định",
        "max_score": 20,
        "criteria": [
            "Chấp hành nội quy và các quy định được áp dụng trong Nhà trường",
        ],
    },
    DRLCategory.DIEU_3.value: {
        "name": "Tham gia các hoạt động chính trị - xã hội, văn hóa - văn nghệ, thể thao; phòng chống tội phạm và tệ nạn xã hội",
        "max_score": 25,
        "criteria": [
            "Tham gia các hoạt động chính trị - xã hội, văn hóa - văn nghệ, thể dục - thể thao",
            "Phòng chống tội phạm và các tệ nạn xã hội",
            "Xây dựng, quảng bá hình ảnh Nhà trường và ĐHQG-HCM",
        ],
    },
    DRLCategory.DIEU_4.value: {
        "name": "Hành động hướng đến xây dựng và phát triển cộng đồng",
        "max_score": 25,
        "criteria": [
            "Chấp hành pháp luật",
            "Tham gia các hoạt động tình nguyện hướng đến cộng đồng, xã hội",
        ],
    },
    DRLCategory.DIEU_5.value: {
        "name": "Các nội dung khuyến khích",
        "max_score": 30,
        "criteria": [
            "Thành tích đặc biệt xuất sắc trong học tập, rèn luyện và nhận được khen thưởng",
            "Có tinh thần vượt khó vươn lên trong học tập và cuộc sống",
            "Có hoàn cảnh đặc biệt",
        ],
    },
}


# =============================================================================
# 3. THỰC THỂ TASK HỢP NHẤT (UNIFIED TASK MODEL - 22 FIELDS)
# =============================================================================

class Task(BaseModel):
    """
    Thực thể Task hợp nhất (22 trường dữ liệu).
    Chuẩn hóa giao diện dữ liệu cho toàn bộ Pipeline:
    Crawler -> SQLite Storage -> RAG / Vector Search -> CP-SAT Scheduler -> UI.
    """

    # -------------------------------------------------------------------------
    # Nhóm 1: Định danh & Siêu dữ liệu mô tả (5 trường)
    # -------------------------------------------------------------------------
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Khóa chính duy nhất (UUID v4 hoặc SHA-1 hash)",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Tiêu đề hoạt động / Tên môn học / Tên bài tập / Tên sự kiện",
    )
    type: TaskType = Field(
        ...,
        description="Phân loại hoạt động (class, assignment, exam, event, personal, tuition)",
    )
    course_code: Optional[str] = Field(
        default=None,
        description="Mã môn học chuẩn hóa (vd: CSC10004)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Mô tả chi tiết, thể lệ cuộc thi hoặc đề bài",
    )

    # -------------------------------------------------------------------------
    # Nhóm 2: Đối tượng & Không gian địa lý (2 trường)
    # -------------------------------------------------------------------------
    target_audience: Optional[str] = Field(
        default=None,
        description="Đối tượng tham gia (K25, Toàn trường, FIT...)",
    )
    location: Optional[str] = Field(
        default=None,
        description="Địa điểm diễn ra (CS1, CS2, Online, MS Teams...)",
    )

    # -------------------------------------------------------------------------
    # Nhóm 3: Mốc thời gian chuẩn hóa datetime ISO 8601 (5 trường)
    # -------------------------------------------------------------------------
    registration_start: Optional[datetime] = Field(
        default=None,
        description="Thời điểm mở đơn đăng ký tham gia",
    )
    registration_end: Optional[datetime] = Field(
        default=None,
        description="Thời điểm đóng đơn đăng ký tham gia",
    )
    start_time: Optional[datetime] = Field(
        default=None,
        description="Thời điểm bắt đầu (áp dụng cho sự kiện cố định)",
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="Thời điểm kết thúc (áp dụng cho sự kiện cố định)",
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Hạn chót nộp bài / hoàn thành / đóng học phí",
    )

    # -------------------------------------------------------------------------
    # Nhóm 4: Điều khiển Lập lịch & Tối ưu hóa ĐRL (4 trường)
    # -------------------------------------------------------------------------
    estimated_hours: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Thời lượng ước tính cần để làm (giờ)",
    )
    training_points: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Số điểm rèn luyện nhận được nếu tham gia",
    )
    drl_category: Optional[DRLCategory] = Field(
        default=None,
        description="Nhóm tiêu chí quy chế ĐRL (dieu_1 đến dieu_5)",
    )
    recurrence: Optional[str] = Field(
        default=None,
        description="Quy tắc lặp chu kỳ (vd: WEEKLY:MON, DAILY)",
    )

    # -------------------------------------------------------------------------
    # Nhóm 5: Vòng đời, Trạng thái & Bảo vệ người dùng (2 trường)
    # -------------------------------------------------------------------------
    status: TaskStatus = Field(
        default=TaskStatus.ACTIVE,
        description="Trạng thái thực hiện (active, done, archived, cancelled)",
    )
    is_manual: bool = Field(
        default=False,
        description="True nếu do người dùng tự tạo/sửa tay (không bị crawler ghi đè)",
    )

    # -------------------------------------------------------------------------
    # Nhóm 6: Nguồn gốc, Đồng bộ & AI Vector (4 trường)
    # -------------------------------------------------------------------------
    source_url: Optional[str] = Field(
        default=None,
        description="Đường dẫn bài viết gốc hoặc link nộp bài trên Moodle",
    )
    source_platform: SourcePlatform = Field(
        default=SourcePlatform.CUSTOM,
        description="Nền tảng nguồn thu thập dữ liệu (moodle, portal, facebook, custom)",
    )
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Vector ngữ nghĩa phục vụ RAG / NLP Semantic Search",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Thời điểm cập nhật bản ghi gần nhất",
    )

    # -------------------------------------------------------------------------
    # VALIDATION LOGIC
    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_task_constraints(self) -> Task:
        """Kiểm tra tính nhất quán logic giữa các thuộc tính."""
        # 1. Ràng buộc thời gian cố định: start_time < end_time
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValueError(
                    f"start_time ({self.start_time}) phải diễn ra trước end_time ({self.end_time})"
                )

        # 2. Ràng buộc mã môn học chuẩn nếu có: regex [A-Z]{3}\\d{5} (vd: CSC10001)
        if self.course_code:
            cleaned_code = self.course_code.strip().upper()
            if re.match(r"^[A-Z]{3}\d{5}$", cleaned_code):
                self.course_code = cleaned_code
            else:
                self.course_code = cleaned_code

        # 3. Sự kiện có điểm ĐRL thì tự động gán Điều 3 nếu thiếu
        if self.training_points > 0 and not self.drl_category:
            self.drl_category = DRLCategory.DIEU_3

        return self

    # =========================================================================
    # CÁC HELPER PROPERTIES PHỤC VỤ TRỰC TIẾP CHO BỘ GIẢI CP-SAT SCHEDULER
    # =========================================================================

    @property
    def duration_minutes(self) -> int:
        """
        Tính thời lượng công việc quy đổi ra phút:
        - Nếu có start_time và end_time: lấy chênh lệch thực tế.
        - Nếu có estimated_hours: lấy estimated_hours * 60.
        - Nếu là sự kiện ĐRL online chỉ có end_time/deadline mà không truyền estimated_hours: mặc định 30 phút.
        - Mặc định: 0 phút.
        """
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return max(1, int(delta.total_seconds() / 60))
        if self.estimated_hours:
            return max(1, int(self.estimated_hours * 60))
        if (
            self.type == TaskType.EVENT
            and self.start_time is None
            and (self.end_time is not None or self.deadline is not None)
        ):
            return 30
        return 0

    @property
    def is_fixed_anchor(self) -> bool:
        """
        Kiểm tra tác vụ có thuộc Tầng 1 (Khối Cố Định / Hard Anchor) trong CP-SAT:
        Gồm: Lịch học TKB, Việc riêng cố định, Giờ ngủ, hoặc slot user tự khóa tay.
        """
        if self.status != TaskStatus.ACTIVE:
            return False
        if self.is_manual and self.start_time and self.end_time:
            return True
        if self.type in (TaskType.CLASS, TaskType.PERSONAL) and self.start_time and self.end_time:
            return True
        return False

    @property
    def is_flexible_task(self) -> bool:
        """
        Kiểm tra tác vụ có thuộc Tầng 2 (Linh hoạt bắt buộc / Flexible Tasks) trong CP-SAT:
        Gồm: Bài tập Moodle, Ôn thi, Đồ án (có deadline + estimated_hours).
        """
        if self.status != TaskStatus.ACTIVE:
            return False
        return bool(
            self.type in (TaskType.ASSIGNMENT, TaskType.EXAM)
            and self.deadline is not None
            and self.estimated_hours is not None
            and self.estimated_hours > 0
        )

    @property
    def is_optional_drl_event(self) -> bool:
        """
        Kiểm tra tác vụ có thuộc Tầng 3 (Sự kiện tùy chọn kiếm ĐRL / Optional Events):
        Hỗ trợ cả 2 hình thái:
        1. Sự kiện cố định khung giờ (Offline / Webinar live): có cả start_time và end_time.
        2. Sự kiện online linh hoạt (Trắc nghiệm / Khảo sát / Minigame): không có start_time,
           chỉ có hạn đóng cổng (end_time hoặc deadline).
        """
        if self.status != TaskStatus.ACTIVE:
            return False
        has_valid_time = (
            (self.start_time is not None and self.end_time is not None)
            or (self.start_time is None and (self.end_time is not None or self.deadline is not None))
        )
        return bool(
            self.type == TaskType.EVENT
            and has_valid_time
            and self.training_points > 0
        )

    @property
    def is_online(self) -> bool:
        """Kiểm tra hoạt động trực tuyến để triệt tiêu thời gian di chuyển (D = 0)."""
        if not self.location:
            return False
        loc = self.location.strip().lower()
        return any(k in loc for k in ("online", "zoom", "teams", "meet", "webinar"))

    # =========================================================================
    # CÁC HÀM TIỆN ÍCH SERIALIZATION CHO SQLITE
    # =========================================================================

    def to_sqlite_tuple(self) -> tuple[Any, ...]:
        """Chuyển đổi thành tuple theo đúng thứ tự 22 cột DDL SQLite để INSERT/UPDATE."""
        return (
            self.id,
            self.title,
            self.type.value if isinstance(self.type, TaskType) else str(self.type),
            self.course_code,
            self.description,
            self.target_audience,
            self.location,
            self.registration_start.isoformat() if self.registration_start else None,
            self.registration_end.isoformat() if self.registration_end else None,
            self.start_time.isoformat() if self.start_time else None,
            self.end_time.isoformat() if self.end_time else None,
            self.deadline.isoformat() if self.deadline else None,
            self.estimated_hours,
            self.training_points,
            self.drl_category.value if isinstance(self.drl_category, DRLCategory) else None,
            self.recurrence,
            self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            1 if self.is_manual else 0,
            self.source_url,
            self.source_platform.value if isinstance(self.source_platform, SourcePlatform) else str(self.source_platform),
            str(self.embedding) if self.embedding else None,
            self.updated_at.isoformat(),
        )

    @classmethod
    def from_sqlite_row(cls, row: dict[str, Any]) -> Task:
        """Tái tạo Task object từ dict dòng dữ liệu SQLite."""
        def parse_dt(val: Any) -> Optional[datetime]:
            if not val:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val))
            except Exception:
                return None

        return cls(
            id=row["id"],
            title=row["title"],
            type=TaskType(row["type"]),
            course_code=row.get("course_code"),
            description=row.get("description"),
            target_audience=row.get("target_audience"),
            location=row.get("location"),
            registration_start=parse_dt(row.get("registration_start")),
            registration_end=parse_dt(row.get("registration_end")),
            start_time=parse_dt(row.get("start_time")),
            end_time=parse_dt(row.get("end_time")),
            deadline=parse_dt(row.get("deadline")),
            estimated_hours=float(row["estimated_hours"]) if row.get("estimated_hours") is not None else None,
            training_points=int(row.get("training_points") or 0),
            drl_category=DRLCategory(row["drl_category"]) if row.get("drl_category") else None,
            recurrence=row.get("recurrence"),
            status=TaskStatus(row.get("status", "active")),
            is_manual=bool(row.get("is_manual", 0)),
            source_url=row.get("source_url"),
            source_platform=SourcePlatform(row.get("source_platform", "custom")),
            embedding=None,
            updated_at=parse_dt(row.get("updated_at")) or datetime.now(),
        )
