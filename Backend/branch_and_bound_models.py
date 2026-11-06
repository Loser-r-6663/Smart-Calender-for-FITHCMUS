"""
Định nghĩa các thực thể dữ liệu, hằng số và hàm tiện ích hỗ trợ cho
Thuật toán Lập lịch Nhánh Cận (Branch and Bound Scheduler).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set


# =============================================================================
# 1. HẰNG SỐ QUY CHẾ ĐIỂM RÈN LUYỆN (HCMUS DRL CAPS & INFO)
# =============================================================================

MAX_TOTAL_DRL: int = 100  # Quy chuẩn trần toàn cục theo quy chế ĐHKHTN (thang 100)

DEFAULT_DRL_CAPS: Dict[str, int] = {
    "dieu_1": 30,  # 1. Tham gia học tập và nghiên cứu khoa học (Tối đa: 30 điểm)
    "dieu_2": 20,  # 2. Chấp hành nội quy, quy chế và các quy định (Tối đa: 20 điểm)
    "dieu_3": 25,  # 3. Hoạt động chính trị - xã hội, VH-VN, TD-TT; phòng chống tội phạm & tệ nạn (Tối đa: 25 điểm)
    "dieu_4": 25,  # 4. Hành động hướng đến xây dựng và phát triển cộng đồng (Tối đa: 25 điểm)
    "dieu_5": 30,  # 5. Các nội dung khuyến khích (Tối đa: 30 điểm)
}

DRL_CATEGORY_NAMES: Dict[str, str] = {
    "dieu_1": "1. Học tập & NCKH",
    "dieu_2": "2. Chấp hành nội quy, quy chế",
    "dieu_3": "3. Chính trị - xã hội, văn thể mỹ, PCTP",
    "dieu_4": "4. Xây dựng & phát triển cộng đồng",
    "dieu_5": "5. Các nội dung khuyến khích",
}

DRL_CATEGORY_FULL_NAMES: Dict[str, str] = {
    "dieu_1": "Tham gia học tập và nghiên cứu khoa học",
    "dieu_2": "Chấp hành nội quy, quy chế và các quy định",
    "dieu_3": "Tham gia các hoạt động chính trị - xã hội, văn hóa - văn nghệ, thể dục - thể thao; phòng chống tội phạm và các tệ nạn xã hội",
    "dieu_4": "Hành động hướng đến xây dựng và phát triển cộng đồng",
    "dieu_5": "Các nội dung khuyến khích",
}

DRL_CATEGORY_CRITERIA: Dict[str, List[str]] = {
    "dieu_1": [
        "Chấp hành các quy định liên quan đến học vụ và khảo thí",
        "Có kết quả học tập tốt và tiến bộ trong mỗi học kỳ",
        "Tích cực tham gia NCKH và các hoạt động học thuật",
    ],
    "dieu_2": [
        "Chấp hành nội quy và các quy định được áp dụng trong Nhà trường",
    ],
    "dieu_3": [
        "Tham gia các hoạt động chính trị - xã hội, văn hóa - văn nghệ, thể dục - thể thao",
        "Phòng chống tội phạm và các tệ nạn xã hội",
        "Xây dựng, quảng bá hình ảnh Nhà trường và ĐHQG-HCM",
    ],
    "dieu_4": [
        "Chấp hành pháp luật",
        "Tham gia các hoạt động tình nguyện hướng đến cộng đồng, xã hội",
    ],
    "dieu_5": [
        "Thành tích đặc biệt xuất sắc trong học tập, rèn luyện và nhận được khen thưởng",
        "Có tinh thần vượt khó vươn lên trong học tập và cuộc sống",
        "Có hoàn cảnh đặc biệt",
    ],
}

FIXED_TASK_TYPES: Set[str] = {"class", "exam", "personal"}


# =============================================================================
# 2. HÀM XỬ LÝ TIỆN ÍCH (HELPERS)
# =============================================================================

def parse_timestamp(value: Any) -> Optional[datetime]:
    """Chuyển đổi linh hoạt timestamp dạng str ISO 8601 hoặc datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except (ValueError, TypeError):
            return None
    return None


def normalize_location(location: Optional[str]) -> str:
    """Chuẩn hóa vị trí địa lý: CS1, CS2 hoặc ONLINE."""
    if not location:
        return "ONLINE"
    loc_upper = str(location).upper()
    if "CS1" in loc_upper or "CƠ SỞ 1" in loc_upper or "NGUYỄN VĂN CỪ" in loc_upper or "QUẬN 5" in loc_upper:
        return "CS1"
    if "CS2" in loc_upper or "CƠ SỞ 2" in loc_upper or "LINH TRUNG" in loc_upper or "THỦ ĐỨC" in loc_upper:
        return "CS2"
    if "ONLINE" in loc_upper or "ZOOM" in loc_upper or "TEAMS" in loc_upper or "MEET" in loc_upper:
        return "ONLINE"
    return "ONLINE"


def get_travel_buffer_minutes(loc1: str, loc2: str, campus_travel_minutes: int = 60) -> int:
    """Thời gian di chuyển tối thiểu giữa 2 địa điểm (mặc định 60 phút giữa CS1 <-> CS2)."""
    norm1, norm2 = normalize_location(loc1), normalize_location(loc2)
    if norm1 == "ONLINE" or norm2 == "ONLINE":
        return 0
    if norm1 != norm2:
        return campus_travel_minutes
    return 0


# =============================================================================
# 3. MÔ HÌNH DỮ LIỆU ĐẦU RA (OUTPUT MODELS)
# =============================================================================

@dataclass
class ScheduledDRLEvent:
    """Đại diện cho một sự kiện ĐRL được chọn trong lịch biểu."""
    task_id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str
    training_points: int
    drl_category: str
    points_gained: int  # Điểm thực nhận sau khi tính trần của Điều đó


@dataclass
class BranchAndBoundResult:
    """Kết quả đầu ra sau khi chạy thuật toán Nhánh Cận."""
    status: str
    selected_events: List[ScheduledDRLEvent]
    total_drl_gained: int
    initial_drl: Dict[str, int]
    final_drl: Dict[str, int]
    drl_caps: Dict[str, int]
    execution_time_seconds: float
    nodes_explored: int
    total_candidates_considered: int
    global_cap: Optional[int] = MAX_TOTAL_DRL

    @property
    def raw_total_drl(self) -> int:
        """Tổng điểm 5 Điều tích lũy."""
        return sum(self.final_drl.values())

    @property
    def final_total_drl(self) -> int:
        """Điểm Rèn Luyện chính thức sau khi áp dụng trần toàn cục (thang 100)."""
        raw = self.raw_total_drl
        return min(self.global_cap, raw) if self.global_cap is not None else raw

    def print_summary(self) -> None:
        """In báo cáo kết quả chi tiết, trực quan."""
        print("=" * 88)
        print("BÁO CÁO KẾT QUẢ LẬP LỊCH TỐI ƯU ĐIỂM RÈN LUYỆN (THUẬT TOÁN NHÁNH CẬN - BRANCH & BOUND)")
        print(f"Trạng thái: {self.status} | Thời gian giải: {self.execution_time_seconds * 1000:.2f} ms | Số nút duyệt: {self.nodes_explored}")
        print("=" * 88)

        print("\n[I] ĐỐI SOÁT ĐIỂM RÈN LUYỆN 5 ĐIỀU (QUY CHẾ ĐHKHTN - ĐHQG-HCM):")
        print("-" * 84)
        print(f"{'Tiêu chí':<10} | {'Tên tiêu chí':<38} | {'Hiện có':<8} | {'Cộng thêm':<10} | {'Tổng sau tuần':<13} | {'Trần tối đa':<10}")
        print("-" * 84)
        for cat in sorted(self.drl_caps.keys()):
            cat_name = DRL_CATEGORY_NAMES.get(cat, cat)
            init_p = self.initial_drl.get(cat, 0)
            final_p = self.final_drl.get(cat, init_p)
            gain = final_p - init_p
            cap = self.drl_caps[cat]
            print(f"{cat:<10} | {cat_name:<38} | {init_p:>6} đ | {f'+{gain} đ':>8} | {final_p:>11} đ | {cap:>8} đ")
        print("-" * 84)
        raw_total = self.raw_total_drl
        official_final = self.final_total_drl
        print(f">>> TỔNG ĐIỂM 5 ĐIỀU TÍCH LŨY: {raw_total} ĐIỂM (TĂNG +{self.total_drl_gained} ĐIỂM) <<<")
        if self.global_cap is not None:
            print(f">>> ĐIỂM RÈN LUYỆN CHÍNH THỨC GHI NHẬN (TRẦN TOÀN CỤC {self.global_cap} ĐIỂM): {official_final} ĐIỂM <<<")

        print(f"\n[II] DANH SÁCH {len(self.selected_events)} HOẠT ĐỘNG ĐRL ĐƯỢC CHỌN (KHÔNG TRÙNG GIỜ HỌC & TỐI ĐA ĐIỂM):")
        if not self.selected_events:
            print("  (Không có sự kiện nào được chọn hoặc không có sự kiện khả thi).")
        for idx, event in enumerate(self.selected_events, 1):
            st_str = event.start_time.strftime("%a %d/%m %H:%M")
            et_str = event.end_time.strftime("%H:%M")
            print(f"  {idx}. [{st_str} -> {et_str}] (+{event.points_gained}đ {event.drl_category}) | {event.title} [{event.location}]")
        print("=" * 88)

