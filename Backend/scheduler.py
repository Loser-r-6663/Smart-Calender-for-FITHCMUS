"""
Phân hệ Lập lịch thông minh (Smart Scheduler) - Đồ án Trợ lý ảo sinh viên FIT - HCMUS.
Hiện thực hóa quy trình 10 bước của thuật toán Google OR-Tools CP-SAT nhằm tối đa hóa
Điểm Rèn Luyện (ĐRL) nhưng vẫn bảo toàn 100% các ràng buộc học vụ và nhịp sinh học:
- Tầng 1: Khối Cố Định (Thời khóa biểu trên lớp, việc riêng cố định, giờ ngủ (user cấu hình))
- Tầng 2: Công Việc Linh Hoạt (Bài tập Moodle, đồ án) & Bữa ăn linh hoạt (Trưa & Tối, user cấu hình)
- Tầng 3: Sự kiện ĐRL Tùy chọn tối ưu theo mô hình Balô Submodular có trần điểm (Điều 1 -> 5)
- Ràng buộc di chuyển phụ thuộc thứ tự và đệm nghỉ giữa các cơ sở đào tạo (CS1 <-> CS2)

Được suy diễn chuẩn mực từ 4 Trụ Cột Tư duy Tính toán trong 'Computational Thinking Steps for CP SAT.md'.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Đảm bảo in tiếng Việt chuẩn UTF-8 trên mọi terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ortools.sat.python import cp_model

from .task_for_running_scheduling_algo import (
        DRL_CATEGORY_CAPS,
        DRL_CATEGORY_INFO,
        DRLCategory,
        SourcePlatform,
        Task,
        TaskStatus,
        TaskType,
)


logger = logging.getLogger(__name__)


# =============================================================================
# 1. CẤU HÌNH THÓI QUEN NGƯỜI DÙNG & RÀNG BUỘC SINH HỌC (USER PREFERENCES)
# =============================================================================

@dataclass
class UserPreferences:
    """
    Cấu hình thói quen sinh học và di chuyển của sinh viên.
    Được nạp từ bảng user_preferences để sinh động (on-the-fly) các khoảng thời gian
    trong bộ nhớ RAM mà không cần lưu thành bản ghi rác trong bảng SQLite tasks.
    Người dùng có thể tùy ý cấu hình các thông số
    """
    # Khung giờ ngủ ban đêm cố định (Mặc định: 23:30 -> 06:30 = 420 phút)
    # Người dùng có thể cấu hình theo (giờ đi ngủ + giờ thức dậy) HOẶC (giờ đi ngủ + sleep_duration_minutes)
    sleep_start_hour: int = 23
    sleep_start_minute: int = 30
    sleep_end_hour: int = 6
    sleep_end_minute: int = 30
    sleep_duration_minutes: Optional[int] = None  # Nếu được truyền (vd: 360p, 480p), sẽ ưu tiên dùng thời lượng này

    # Khung giờ ăn trưa linh hoạt (Mặc định cửa sổ: 11:00 -> 13:30, thời lượng 45 phút)
    lunch_window_start_hour: int = 11
    lunch_window_start_minute: int = 0
    lunch_window_end_hour: int = 13
    lunch_window_end_minute: int = 30
    lunch_duration_minutes: int = 45

    # Khung giờ ăn tối linh hoạt (Mặc định cửa sổ: 17:30 -> 20:00, thời lượng 60 phút)
    dinner_window_start_hour: int = 17
    dinner_window_start_minute: int = 30
    dinner_window_end_hour: int = 20
    dinner_window_end_minute: int = 0
    dinner_duration_minutes: int = 60

    # Di chuyển giữa các cơ sở đào tạo (CS1 Nguyễn Văn Cừ Q5 <-> CS2 Linh Trung Thủ Đức)
    campus_travel_minutes: int = 50
    rest_buffer_minutes: int = 15

    # Giới hạn chống kiệt sức (Anti-Burnout)
    max_work_hours_per_day: float = 11.0

    def get_sleep_interval_for_day(self, day_k: int) -> Tuple[int, int, int]:
        """
        Tính mốc phút bắt đầu ngủ, kết thúc ngủ và thời lượng ngủ của đêm ngày day_k (0 = Thứ Hai ... 6 = Chủ Nhật).
        Hỗ trợ cả trường hợp đi ngủ trước nửa đêm (vd: 22:30, 23:30) lẫn sau nửa đêm (vd: 00:30, 01:00),
        và ưu tiên sleep_duration_minutes nếu người dùng cấu hình trực tiếp thời lượng ngủ.
        """
        if self.sleep_start_hour >= 12:
            # Đi ngủ vào buổi tối ngày day_k (vd: 22:00, 23:30)
            night_start = day_k * 1440 + self.sleep_start_hour * 60 + self.sleep_start_minute
        else:
            # Đi ngủ sau nửa đêm (rạng sáng ngày day_k + 1, vd: 00:30, 01:00)
            night_start = (day_k + 1) * 1440 + self.sleep_start_hour * 60 + self.sleep_start_minute

        if self.sleep_duration_minutes is not None:
            sleep_dur = max(0, self.sleep_duration_minutes)
            night_end = night_start + sleep_dur
        else:
            night_end = (day_k + 1) * 1440 + self.sleep_end_hour * 60 + self.sleep_end_minute
            if night_end <= night_start:
                night_end += 1440
            sleep_dur = night_end - night_start

        return night_start, night_end, sleep_dur


# =============================================================================
# 2. CẤU TRÚC KẾT QUẢ ĐẦU RA CỦA BỘ LẬP LỊCH (SCHEDULE OUTPUT MODELS)
# =============================================================================

@dataclass
class ScheduledItem:
    """Đại diện cho một hoạt động đã được bộ giải ấn định thời gian trên lịch."""
    task_id: str
    title: str
    item_type: str  # Phân loại: 'class' (học), 'assignment' (bài tập), 'event' (ĐRL), 'meal' (ăn), 'sleep' (ngủ), 'personal' (việc riêng)
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    location: Optional[str] = None
    training_points: int = 0
    drl_category: Optional[str] = None
    details: Optional[str] = None


@dataclass
class ScheduleResult:
    """Tổng hợp kết quả lập lịch tối ưu trả về cho giao diện UI Calendar."""
    status: str  # Trạng thái giải: 'OPTIMAL' (Tối ưu), 'FEASIBLE' (Khả thi), 'INFEASIBLE' (Vô nghiệm), 'TIMEOUT' (Hết giờ)
    solve_time_seconds: float
    total_drl_gained: int
    drl_gained_by_category: Dict[str, int] = field(default_factory=dict)
    scheduled_items: List[ScheduledItem] = field(default_factory=list)
    selected_event_ids: List[str] = field(default_factory=list)
    scheduled_assignment_slots: List[ScheduledItem] = field(default_factory=list)
    message: str = ""
    solver_stats: str = ""  # Thống kê chi tiết từ bộ giải CP-SAT (số nhánh, xung đột, thời gian, bộ nhớ)


# =============================================================================
# 3. CÁC HÀM TIỆN ÍCH QUY ĐỔI THỜI GIAN & KHÔNG GIAN ĐỊA LÝ
# =============================================================================

def dt_to_minute(dt: datetime, horizon_start: datetime) -> int:
    """Chuyển đổi datetime sang số phút tính từ mốc bắt đầu tuần (horizon_start)."""
    delta = dt - horizon_start
    return int(delta.total_seconds() // 60)


def minute_to_dt(minute: int, horizon_start: datetime) -> datetime:
    """Chuyển đổi số phút trên trục thời gian trở lại đối tượng datetime chuẩn."""
    return horizon_start + timedelta(minutes=minute)


def normalize_location(location: Optional[str]) -> str:
    """
    Chuẩn hóa địa điểm về 3 nhóm phục vụ tính toán di chuyển:
    - 'ONLINE': Các buổi học/sự kiện qua mạng (Zoom, MS Teams, Google Meet) -> Thời gian di chuyển D = 0.
    - 'CS1': Cơ sở Nguyễn Văn Cừ, Quận 5.
    - 'CS2': Cơ sở Linh Trung, TP. Thủ Đức.
    """
    if not location:
        return "CS1"  # Mặc định là cơ sở chính nếu không ghi rõ
    loc = location.strip().lower()
    if any(k in loc for k in ("online", "zoom", "teams", "meet", "webinar", "trực tuyến")):
        return "ONLINE"
    if any(k in loc for k in ("cs2", "linh trung", "thủ đức", "thu duc")):
        return "CS2"
    if any(k in loc for k in ("cs1", "nguyễn văn cừ", "nguyen van cu", "quận 5")):
        return "CS1"
    return "CS1"


def get_travel_time(loc_a: str, loc_b: str, prefs: UserPreferences) -> int:
    """
    Tính thời gian di chuyển và đệm nghỉ giữa 2 địa điểm:
    - Nếu 1 trong 2 là ONLINE hoặc cùng cơ sở: 0 phút.
    - Nếu khác cơ sở (CS1 <-> CS2): campus_travel_minutes + rest_buffer_minutes.
    """
    norm_a = normalize_location(loc_a)
    norm_b = normalize_location(loc_b)
    if norm_a == "ONLINE" or norm_b == "ONLINE":
        return 0
    if norm_a == norm_b:
        return 0
    return prefs.campus_travel_minutes + prefs.rest_buffer_minutes


# =============================================================================
# 4. THUẬT TOÁN LẬP LỊCH CHÍNH (GOOGLE OR-TOOLS CP-SAT SCHEDULER PIPELINE)
# =============================================================================

def solve_max_drl_schedule(
    tasks: List[Task],
    week_start: date | datetime,
    now: Optional[datetime] = None,
    current_drl_points: Optional[Dict[str, int]] = None,
    preferences: Optional[UserPreferences] = None,
    timeout_seconds: float = 3.0,
    log_search_progress: bool = False,
) -> ScheduleResult:
    """
    Thực thi 10 bước của quy trình Tư duy Tính toán CP-SAT để lập lịch tuần tối ưu:
    1. Chuẩn hóa trục thời gian 1 tuần [0, 10080 phút].
    2. Khóa cứng khoảng quá khứ [0, now].
    3. Thiết lập Tầng 1 - Khối Cố Định (TKB, việc riêng, khóa tay) & Sinh động Giờ ngủ 23:30 - 06:30.
    4. Sinh động Tầng 2 - Bữa ăn linh hoạt (Bữa trưa 45p, Bữa tối 60p).
    5. Thiết lập Tầng 2 - Công việc linh hoạt bắt buộc (Bài tập Moodle, Đồ án trước hạn chót).
    6. Thiết lập Tầng 3 - Sự kiện ĐRL tùy chọn tối ưu (Gắn biến Boolean x_i).
    7. Ràng buộc loại trừ lẫn nhau toàn cục (Disjunctive No-Overlap).
    8. Ràng buộc di chuyển địa lý giữa các cơ sở kèm đệm nghỉ (CS1 <-> CS2).
    9. Hàm mục tiêu Balô Submodular có trần điểm 5 Điều (DRL_CATEGORY_CAPS).
    10. Giải với CP-SAT đa luồng (2 workers) và trích xuất lịch trình tối ưu.
    """
    start_solve_ts = datetime.now()

    if preferences is None:
        preferences = UserPreferences()

    if current_drl_points is None:
        current_drl_points = {}

    # Chuẩn hóa mốc đầu tuần (horizon_start: Thứ Hai 00:00:00)
    if isinstance(week_start, datetime):
        horizon_start = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
    else:
        horizon_start = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)

    horizon_end = horizon_start + timedelta(days=7)
    horizon_limit_minutes = 10080  # 7 ngày * 24 giờ * 60 phút

    # Mốc thời gian hiện tại
    if now is None:
        now = horizon_start
    t_now = max(0, min(horizon_limit_minutes, dt_to_minute(now, horizon_start)))

    # -------------------------------------------------------------------------
    # BƯỚC 1: KHỞI TẠO MÔ HÌNH CP-SAT MODEL
    # -------------------------------------------------------------------------
    model = cp_model.CpModel()
    all_intervals: List[Any] = []

    # -------------------------------------------------------------------------
    # BƯỚC 2: KHÓA CỨNG VÙNG THỜI GIAN QUÁ KHỨ (KHOẢNG [0, now])
    # -------------------------------------------------------------------------
    if t_now > 0:
        past_interval = model.NewIntervalVar(0, t_now, t_now, "past_horizon")
        all_intervals.append(past_interval)

    # -------------------------------------------------------------------------
    # BƯỚC 3: TẦNG 1 — CÁC KHỐI CỐ ĐỊNH & SINH ĐỘNG GIỜ NGỦ BAN ĐÊM (23:30 -> 06:30)
    # -------------------------------------------------------------------------
    fixed_tasks_records: List[Tuple[Task, int, int]] = []
    for t in tasks:
        if t.is_fixed_anchor:
            s_min = dt_to_minute(t.start_time, horizon_start)  # type: ignore
            e_min = dt_to_minute(t.end_time, horizon_start)    # type: ignore
            
            # Cắt gọn trong tuần lập lịch nếu cần
            s_clamped = max(0, s_min)
            e_clamped = min(horizon_limit_minutes, e_min)
            dur = e_clamped - s_clamped
            if dur > 0 and e_clamped > t_now:
                # Nếu đã trôi vào quá khứ một phần, chỉ xét phần tương lai
                eff_start = max(t_now, s_clamped)
                eff_dur = e_clamped - eff_start
                if eff_dur > 0:
                    fixed_int = model.NewIntervalVar(eff_start, eff_dur, e_clamped, f"fixed_{t.id}")
                    all_intervals.append(fixed_int)
                    fixed_tasks_records.append((t, s_min, e_min))

    # Sinh động Giờ ngủ ban đêm bảo vệ nhịp sinh học theo cấu hình người dùng (đủ 7 đêm)
    # Đêm trước đầu tuần (Chủ Nhật rạng sáng Thứ Hai: day_k = -1)
    prev_night_start, mon_morning_sleep_end, prev_sleep_dur = preferences.get_sleep_interval_for_day(-1)
    if prev_sleep_dur > 0 and mon_morning_sleep_end > t_now:
        sleep_start = max(t_now, 0, prev_night_start)
        sleep_dur = mon_morning_sleep_end - sleep_start
        if sleep_dur > 0:
            int_sleep_mon = model.NewIntervalVar(
                sleep_start, sleep_dur, mon_morning_sleep_end, "sleep_mon_morning"
            )
            all_intervals.append(int_sleep_mon)

    # 7 đêm k = 0 (Thứ Hai) đến k = 6 (Chủ Nhật)
    for day_k in range(7):
        night_start, night_end, cfg_sleep_dur = preferences.get_sleep_interval_for_day(day_k)
        if cfg_sleep_dur <= 0:
            continue
        night_end_clamped = min(horizon_limit_minutes, night_end)

        if night_end_clamped > t_now and night_start < horizon_limit_minutes:
            eff_sleep_start = max(t_now, night_start)
            eff_sleep_dur = night_end_clamped - eff_sleep_start
            if eff_sleep_dur > 0:
                int_sleep = model.NewIntervalVar(
                    eff_sleep_start, eff_sleep_dur, night_end_clamped, f"sleep_night_{day_k}"
                )
                all_intervals.append(int_sleep)

    # -------------------------------------------------------------------------
    # BƯỚC 4: TẦNG 2 — SINH ĐỘNG BỮA ĂN LINH HOẠT (CỬA SỔ TRƯỢT TRƯA & TỐI)
    # -------------------------------------------------------------------------
    lunch_vars: List[Tuple[int, cp_model.IntVar, cp_model.IntVar, Any]] = []
    dinner_vars: List[Tuple[int, cp_model.IntVar, cp_model.IntVar, Any]] = []

    for day_k in range(7):
        day_offset = day_k * 1440

        # A. Bữa trưa (Tùy chỉnh khung giờ và thời lượng theo preferences)
        lunch_dur = preferences.lunch_duration_minutes
        if lunch_dur > 0:
            lunch_w_start = day_offset + preferences.lunch_window_start_hour * 60 + preferences.lunch_window_start_minute
            lunch_w_end = day_offset + preferences.lunch_window_end_hour * 60 + preferences.lunch_window_end_minute
            latest_lunch_start = lunch_w_end - lunch_dur

            if latest_lunch_start >= t_now:
                earliest_start = max(t_now, lunch_w_start)
                if earliest_start <= latest_lunch_start:
                    s_lunch = model.NewIntVar(earliest_start, latest_lunch_start, f"s_lunch_{day_k}")
                    e_lunch = model.NewIntVar(earliest_start + lunch_dur, lunch_w_end, f"e_lunch_{day_k}")
                    int_lunch = model.NewIntervalVar(s_lunch, lunch_dur, e_lunch, f"lunch_{day_k}")
                    all_intervals.append(int_lunch)
                    lunch_vars.append((day_k, s_lunch, e_lunch, int_lunch))

        # B. Bữa tối (Tùy chỉnh khung giờ và thời lượng theo preferences)
        dinner_dur = preferences.dinner_duration_minutes
        if dinner_dur > 0:
            dinner_w_start = day_offset + preferences.dinner_window_start_hour * 60 + preferences.dinner_window_start_minute
            dinner_w_end = day_offset + preferences.dinner_window_end_hour * 60 + preferences.dinner_window_end_minute
            latest_dinner_start = dinner_w_end - dinner_dur

            if latest_dinner_start >= t_now:
                earliest_dinner_start = max(t_now, dinner_w_start)
                if earliest_dinner_start <= latest_dinner_start:
                    s_dinner = model.NewIntVar(earliest_dinner_start, latest_dinner_start, f"s_dinner_{day_k}")
                    e_dinner = model.NewIntVar(earliest_dinner_start + dinner_dur, dinner_w_end, f"e_dinner_{day_k}")
                    int_dinner = model.NewIntervalVar(s_dinner, dinner_dur, e_dinner, f"dinner_{day_k}")
                    all_intervals.append(int_dinner)
                    dinner_vars.append((day_k, s_dinner, e_dinner, int_dinner))

    # -------------------------------------------------------------------------
    # BƯỚC 5: TẦNG 2 — CÔNG VIỆC LINH HOẠT BẮT BUỘC (BÀI TẬP MOODLE, ĐỒ ÁN)
    # -------------------------------------------------------------------------
    assignment_vars: List[Tuple[Task, cp_model.IntVar, cp_model.IntVar, Any]] = []
    impossible_assignments: List[str] = []

    for t in tasks:
        if t.is_flexible_task:
            p_min = t.duration_minutes
            deadline_min = dt_to_minute(t.deadline, horizon_start)  # type: ignore
            deadline_clamped = min(horizon_limit_minutes, deadline_min)

            # Kiểm tra tính khả thi cơ bản trước khi nạp vào solver
            if deadline_clamped < t_now + p_min:
                impossible_assignments.append(
                    f"{t.title} (Cần {p_min}p nhưng hạn chót đã trôi qua hoặc quá sát)"
                )
                continue

            earliest_start = t_now
            latest_start = deadline_clamped - p_min
            s_assign = model.NewIntVar(earliest_start, latest_start, f"s_assign_{t.id}")
            e_assign = model.NewIntVar(earliest_start + p_min, deadline_clamped, f"e_assign_{t.id}")
            int_assign = model.NewIntervalVar(s_assign, p_min, e_assign, f"assign_{t.id}")

            all_intervals.append(int_assign)
            assignment_vars.append((t, s_assign, e_assign, int_assign))

    if impossible_assignments:
        msg = "Không thể xếp lịch vì có bài tập vi phạm hạn chót: " + "; ".join(impossible_assignments)
        logger.warning(msg)
        return ScheduleResult(
            status="INFEASIBLE",
            solve_time_seconds=0.0,
            total_drl_gained=0,
            message=msg,
        )

    # -------------------------------------------------------------------------
    # BƯỚC 6: TẦNG 3 — SỰ KIỆN TÙY CHỌN TỐI ƯU ĐIỂM RÈN LUYỆN (GẮN BIẾN BOOLEAN x_i)
    # -------------------------------------------------------------------------
    # Hỗ trợ 2 hình thái sự kiện ĐRL:
    # - Hình thái 1 (Cố định giờ): Có cả start_time và end_time -> s_min, e_min là hằng số int.
    # - Hình thái 2 (Linh hoạt/Online chỉ có hạn đóng): start_time = None, chỉ có end_time/deadline
    #   -> s_var, e_var là biến nguyên IntVar trôi nổi trong [t_now, end_limit].
    event_vars: List[Tuple[Task, cp_model.IntVar, Any, Any, Any]] = []
    flexible_event_start_vars: List[cp_model.IntVar] = []

    for t in tasks:
        if t.is_optional_drl_event:
            # Hình thái 1: Sự kiện có khung giờ bắt đầu và kết thúc cố định
            if t.start_time is not None and t.end_time is not None:
                s_min = dt_to_minute(t.start_time, horizon_start)
                e_min = dt_to_minute(t.end_time, horizon_start)

                # Nếu sự kiện đã trôi qua trước t_now hoặc nằm ngoài tuần thì bỏ qua
                if e_min <= t_now or s_min >= horizon_limit_minutes or s_min < 0:
                    continue

                dur = e_min - s_min
                if dur <= 0:
                    continue

                # Biến Boolean x_i: 1 nếu chọn đi sự kiện, 0 nếu không đi
                x_i = model.NewBoolVar(f"select_event_{t.id}")
                opt_int = model.NewOptionalIntervalVar(s_min, dur, e_min, x_i, f"event_{t.id}")
                all_intervals.append(opt_int)
                event_vars.append((t, x_i, s_min, e_min, opt_int))

            # Hình thái 2: Sự kiện online không có start_time, chỉ có end_time hoặc deadline
            elif t.start_time is None and (t.end_time is not None or t.deadline is not None):
                eff_end_dt = t.end_time if t.end_time is not None else t.deadline
                end_limit_min = min(horizon_limit_minutes, dt_to_minute(eff_end_dt, horizon_start))  # type: ignore
                dur = t.duration_minutes

                # Nếu hạn đóng sự kiện không đủ thời lượng thực hiện từ t_now thì bỏ qua
                if dur <= 0 or end_limit_min < t_now + dur:
                    continue

                x_i = model.NewBoolVar(f"select_flex_event_{t.id}")
                s_var = model.NewIntVar(t_now, end_limit_min - dur, f"s_flex_event_{t.id}")
                e_var = model.NewIntVar(t_now + dur, end_limit_min, f"e_flex_event_{t.id}")
                opt_int = model.NewOptionalIntervalVar(s_var, dur, e_var, x_i, f"flex_event_{t.id}")

                all_intervals.append(opt_int)
                event_vars.append((t, x_i, s_var, e_var, opt_int))
                flexible_event_start_vars.append(s_var)

    # -------------------------------------------------------------------------
    # BƯỚC 7: RÀNG BUỘC LOẠI TRỪ LẪN NHAU TOÀN CỤC (KHÔNG TRÙNG LỊCH - ADD_NO_OVERLAP)
    # -------------------------------------------------------------------------
    model.AddNoOverlap(all_intervals)

    # -------------------------------------------------------------------------
    # BƯỚC 8: RÀNG BUỘC DI CHUYỂN GIỮA CÁC CƠ SỞ ĐÀO TẠO KÈM ĐỆM NGHỈ (CS1 <-> CS2)
    # -------------------------------------------------------------------------
    # A. Giữa cặp 2 sự kiện ĐRL tùy chọn i và k (Chỉ xét các sự kiện có mốc giờ cố định offline)
    num_events = len(event_vars)
    for i in range(num_events):
        task_i, x_i, s_i, e_i, _ = event_vars[i]
        if not (isinstance(s_i, int) and isinstance(e_i, int)):
            continue
        for k in range(i + 1, num_events):
            task_k, x_k, s_k, e_k, _ = event_vars[k]
            if not (isinstance(s_k, int) and isinstance(e_k, int)):
                continue
            travel_ik = get_travel_time(task_i.location, task_k.location, preferences)
            if travel_ik > 0:
                # Nếu i kết thúc trước k mà không kịp di chuyển
                if e_i <= s_k < e_i + travel_ik:
                    model.AddBoolOr([x_i.Not(), x_k.Not()])
                # Nếu k kết thúc trước i mà không kịp di chuyển
                elif e_k <= s_i < e_k + travel_ik:
                    model.AddBoolOr([x_i.Not(), x_k.Not()])

    # B. Giữa sự kiện ĐRL tùy chọn i và Khối cố định m (Lịch học TKB)
    for task_i, x_i, s_i, e_i, _ in event_vars:
        if not (isinstance(s_i, int) and isinstance(e_i, int)):
            continue
        for fixed_task, s_m, e_m in fixed_tasks_records:
            travel_im = get_travel_time(task_i.location, fixed_task.location, preferences)
            if travel_im > 0:
                # Học xong ở m, chạy qua sự kiện i không kịp
                if e_m <= s_i < e_m + travel_im:
                    model.Add(x_i == 0)
                # Đi sự kiện i xong, chạy về học ở m không kịp
                elif e_i <= s_m < e_i + travel_im:
                    model.Add(x_i == 0)

    # -------------------------------------------------------------------------
    # BƯỚC 9: HÀM MỤC TIÊU BALÔ SUBMODULAR CÓ TRẦN ĐIỂM (LỢI ÍCH BIÊN GIẢM DẦN THEO 5 ĐIỀU)
    # -------------------------------------------------------------------------
    categories = [
        DRLCategory.DIEU_1.value,
        DRLCategory.DIEU_2.value,
        DRLCategory.DIEU_3.value,
        DRLCategory.DIEU_4.value,
        DRLCategory.DIEU_5.value,
    ]

    gain_vars: Dict[str, cp_model.IntVar] = {}
    for cat in categories:
        cap_cat = DRL_CATEGORY_CAPS.get(cat, 25)
        current_cat = current_drl_points.get(cat, 0)
        remaining_cat = max(0, cap_cat - current_cat)

        cat_events = [ev for ev in event_vars if (ev[0].drl_category and ev[0].drl_category.value == cat)]

        if remaining_cat > 0 and cat_events:
            gain_c = model.NewIntVar(0, remaining_cat, f"gain_{cat}")
            raw_sum_expr = sum(ev[0].training_points * ev[1] for ev in cat_events)
            model.AddMinEquality(gain_c, [raw_sum_expr, remaining_cat])
            gain_vars[cat] = gain_c
        elif remaining_cat > 0:
            gain_vars[cat] = model.NewIntVar(0, 0, f"gain_{cat}_zero")
        else:
            gain_vars[cat] = model.NewIntVar(0, 0, f"gain_{cat}_capped")

    # Mục tiêu chính: Tối đa hóa tổng điểm ĐRL thực tế tăng thêm
    total_gain_expr = sum(gain_vars[cat] for cat in categories)

    # Mục tiêu phụ (Tie-Breaker): Ưu tiên làm bài tập và sự kiện online sớm hơn nếu có slot trống
    # Trọng số: 1_000_000 * ĐRL - early_start_penalty
    # Đảm bảo 1 điểm ĐRL (1_000_000) luôn áp đảo toàn bộ tổng phút của tuần
    all_flexible_starts = [s_assign for _, s_assign, _, _ in assignment_vars] + flexible_event_start_vars
    early_start_penalty = sum(all_flexible_starts) if all_flexible_starts else 0
    model.Maximize(1_000_000 * total_gain_expr - early_start_penalty)

    # -------------------------------------------------------------------------
    # BƯỚC 10: CẤU HÌNH ĐA LUỒNG VÀ GỌI BỘ GIẢI GOOGLE OR-TOOLS CP-SAT
    # -------------------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 2  # Tối ưu hóa cho 3 nhân CPU máy trạm sinh viên
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.log_search_progress = log_search_progress

    solve_status = solver.Solve(model)
    solve_duration = (datetime.now() - start_solve_ts).total_seconds()

    if solve_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status_str = "INFEASIBLE" if solve_status == cp_model.INFEASIBLE else "TIMEOUT"
        return ScheduleResult(
            status=status_str,
            solve_time_seconds=solve_duration,
            total_drl_gained=0,
            message="Không tìm thấy phương án lập lịch khả thi thỏa mãn toàn bộ ràng buộc.",
            solver_stats=solver.ResponseStats(),
        )

    # -------------------------------------------------------------------------
    # TRÍCH XUẤT VÀ TỔNG HỢP KẾT QUẢ ĐẦU RA CHO GIAO DIỆN LỊCH
    # -------------------------------------------------------------------------
    scheduled_items: List[ScheduledItem] = []
    selected_event_ids: List[str] = []
    scheduled_assignment_slots: List[ScheduledItem] = []

    # 1. Trích xuất các Khối Cố Định (Fixed Tasks)
    for t in tasks:
        if t.is_fixed_anchor and t.start_time and t.end_time:
            scheduled_items.append(
                ScheduledItem(
                    task_id=t.id,
                    title=t.title,
                    item_type=t.type.value,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    duration_minutes=t.duration_minutes,
                    location=t.location,
                    training_points=0,
                    drl_category=None,
                    details=f"Cố định [{t.course_code or ''}] {t.location or ''}".strip(),
                )
            )

    # 2. Trích xuất Giờ ngủ (Sleep Anchors)
    for day_k in range(7):
        night_start, night_end, cfg_sleep_dur = preferences.get_sleep_interval_for_day(day_k)
        if cfg_sleep_dur <= 0:
            continue
        s_dt = minute_to_dt(night_start, horizon_start)
        e_dt = minute_to_dt(night_end, horizon_start)
        sleep_hours_str = f"{cfg_sleep_dur / 60:.1f}".rstrip("0").rstrip(".")
        scheduled_items.append(
            ScheduledItem(
                task_id=f"sleep_night_{day_k}",
                title=f"Giấc ngủ đêm (Thứ {day_k + 2 if day_k < 6 else 'CN'})",
                item_type="sleep",
                start_time=s_dt,
                end_time=e_dt,
                duration_minutes=cfg_sleep_dur,
                location="Nhà / KTX",
                details=f"Bảo vệ nhịp sinh học & chống kiệt sức ({sleep_hours_str} tiếng)",
            )
        )

    # 3. Trích xuất Bữa ăn linh hoạt (Floating Meals)
    for day_k, s_lunch, e_lunch, _ in lunch_vars:
        s_val = solver.Value(s_lunch)
        e_val = solver.Value(e_lunch)
        scheduled_items.append(
            ScheduledItem(
                task_id=f"lunch_{day_k}",
                title=f"Bữa trưa (Thứ {day_k + 2 if day_k < 6 else 'CN'})",
                item_type="meal",
                start_time=minute_to_dt(s_val, horizon_start),
                end_time=minute_to_dt(e_val, horizon_start),
                duration_minutes=e_val - s_val,
                location=None,
                details="Tự động luồn lách giữa ca học sáng và chiều",
            )
        )

    for day_k, s_dinner, e_dinner, _ in dinner_vars:
        s_val = solver.Value(s_dinner)
        e_val = solver.Value(e_dinner)
        scheduled_items.append(
            ScheduledItem(
                task_id=f"dinner_{day_k}",
                title=f"Bữa tối (Thứ {day_k + 2 if day_k < 6 else 'CN'})",
                item_type="meal",
                start_time=minute_to_dt(s_val, horizon_start),
                end_time=minute_to_dt(e_val, horizon_start),
                duration_minutes=e_val - s_val,
                location=None,
                details="Tự động luồn lách giữa ca học chiều và tối",
            )
        )

    # 4. Trích xuất Lịch làm bài tập (Assignments)
    for t, s_assign, e_assign, _ in assignment_vars:
        s_val = solver.Value(s_assign)
        e_val = solver.Value(e_assign)
        item = ScheduledItem(
            task_id=t.id,
            title=f"Làm bài: {t.title}",
            item_type=t.type.value,
            start_time=minute_to_dt(s_val, horizon_start),
            end_time=minute_to_dt(e_val, horizon_start),
            duration_minutes=e_val - s_val,
            location=t.location or "Bàn học / Thư viện",
            details=f"Hạn nộp: {t.deadline.strftime('%H:%M %d/%m') if t.deadline else ''}",
        )
        scheduled_items.append(item)
        scheduled_assignment_slots.append(item)

    # 5. Trích xuất Sự kiện ĐRL được chọn (Selected Events)
    total_gained = 0
    drl_gained_by_cat: Dict[str, int] = {}
    for cat in categories:
        val = solver.Value(gain_vars[cat])
        drl_gained_by_cat[cat] = val
        total_gained += val

    for t, x_i, s_min_or_var, e_min_or_var, _ in event_vars:
        if solver.Value(x_i) == 1:
            s_val = s_min_or_var if isinstance(s_min_or_var, int) else solver.Value(s_min_or_var)
            e_val = e_min_or_var if isinstance(e_min_or_var, int) else solver.Value(e_min_or_var)
            selected_event_ids.append(t.id)
            scheduled_items.append(
                ScheduledItem(
                    task_id=t.id,
                    title=f"ĐRL (+{t.training_points}): {t.title}",
                    item_type=t.type.value,
                    start_time=minute_to_dt(s_val, horizon_start),
                    end_time=minute_to_dt(e_val, horizon_start),
                    duration_minutes=e_val - s_val,
                    location=t.location or "Online",
                    training_points=t.training_points,
                    drl_category=t.drl_category.value if t.drl_category else None,
                    details=f"Điểm thưởng: +{t.training_points} [{t.drl_category.value if t.drl_category else ''}]",
                )
            )

    # Sắp xếp toàn bộ lịch trình theo mốc bắt đầu tăng dần
    scheduled_items.sort(key=lambda item: item.start_time)

    status_str = "OPTIMAL" if solve_status == cp_model.OPTIMAL else "FEASIBLE"
    msg = (
        f"Lập lịch thành công ({status_str}) trong {solve_duration:.3f}s! "
        f"Thu thập được +{total_gained} Điểm Rèn Luyện, chọn {len(selected_event_ids)} sự kiện."
    )

    return ScheduleResult(
        status=status_str,
        solve_time_seconds=solve_duration,
        total_drl_gained=total_gained,
        drl_gained_by_category=drl_gained_by_cat,
        scheduled_items=scheduled_items,
        selected_event_ids=selected_event_ids,
        scheduled_assignment_slots=scheduled_assignment_slots,
        message=msg,
        solver_stats=solver.ResponseStats(),
    )
