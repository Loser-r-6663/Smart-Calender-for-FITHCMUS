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

DEFAULT_DRL_CAPS: Dict[str, int] = {
    "dieu_1": 25,  # 1. Chấp hành pháp luật và nội quy, quy chế nhà trường (Tối đa: 25 điểm)
    "dieu_2": 20,  # 2. Tinh thần và thái độ trong học tập, NCKH (Tối đa: 20 điểm)
    "dieu_3": 20,  # 3. Chính trị - Xã hội, Thể thao, Văn nghệ (Tối đa: 20 điểm)
    "dieu_4": 15,  # 4. Trách nhiệm công dân trong quan hệ cộng đồng (Tối đa: 15 điểm)
    "dieu_5": 20,  # 5. Cán bộ lớp, đoàn thể, khen thưởng (Tối đa: 20 điểm)
}

DRL_CATEGORY_NAMES: Dict[str, str] = {
    "dieu_1": "1. Chấp hành pháp luật & nội quy",
    "dieu_2": "2. Học tập & nghiên cứu khoa học",
    "dieu_3": "3. Chính trị - xã hội, văn thể mỹ",
    "dieu_4": "4. Quan hệ cộng đồng, tình nguyện",
    "dieu_5": "5. Cán bộ lớp, đoàn thể, khen thưởng",
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

    def print_summary(self) -> None:
        """In báo cáo kết quả chi tiết, trực quan."""
        print("=" * 88)
        print("BÁO CÁO KẾT QUẢ LẬP LỊCH TỐI ƯU ĐIỂM RÈN LUYỆN (THUẬT TOÁN NHÁNH CẬN - BRANCH & BOUND)")
        print(f"Trạng thái: {self.status} | Thời gian giải: {self.execution_time_seconds * 1000:.2f} ms | Số nút duyệt: {self.nodes_explored}")
        print("=" * 88)

        print("\n[I] ĐỐI SOÁT ĐIỂM RÈN LUYỆN 5 ĐIỀU (QUY CHẾ ĐHKHTN - ĐHQG-HCM):")
        print("-" * 78)
        print(f"{'Tiêu chí':<10} | {'Tên tiêu chí':<35} | {'Hiện có':<8} | {'Cộng thêm':<10} | {'Tổng sau tuần':<13} | {'Trần tối đa':<10}")
        print("-" * 78)
        for cat in sorted(self.drl_caps.keys()):
            cat_name = DRL_CATEGORY_NAMES.get(cat, cat)
            init_p = self.initial_drl.get(cat, 0)
            final_p = self.final_drl.get(cat, init_p)
            gain = final_p - init_p
            cap = self.drl_caps[cat]
            print(f"{cat:<10} | {cat_name:<35} | {init_p:>6} đ | {f'+{gain} đ':>8} | {final_p:>11} đ | {cap:>8} đ")
        print("-" * 78)
        print(f">>> TỔNG ĐIỂM RÈN LUYỆN THỰC TẾ TĂNG THÊM: +{self.total_drl_gained} ĐIỂM <<<")

        print(f"\n[II] DANH SÁCH {len(self.selected_events)} HOẠT ĐỘNG ĐRL ĐƯỢC CHỌN (KHÔNG TRÙNG GIỜ HỌC & TỐI ĐA ĐIỂM):")
        if not self.selected_events:
            print("  (Không có sự kiện nào được chọn hoặc không có sự kiện khả thi).")
        for idx, event in enumerate(self.selected_events, 1):
            st_str = event.start_time.strftime("%a %d/%m %H:%M")
            et_str = event.end_time.strftime("%H:%M")
            print(f"  {idx}. [{st_str} -> {et_str}] (+{event.points_gained}đ {event.drl_category}) | {event.title} [{event.location}]")
        print("=" * 88)

