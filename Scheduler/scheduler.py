import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone

from DataProcessor.Standardization.BaseTask import DateDayTime, Location
from DataProcessor.Standardization.Task import Task

VN_TZ = timezone(timedelta(hours=7))

DEFAULT_DRL_CAPS: dict[str, int] = {
    "Articles 1": 30,  # Học tập & NCKH
    "Articles 2": 20,  # Kỷ luật, nội quy
    "Articles 3": 25,  # Hoạt động Đoàn - Hội, văn thể mỹ
    "Articles 4": 25,  # Cộng đồng, tình nguyện
    "Articles 5": 30,  # Khuyến khích
}
MAX_TOTAL_DRL: int = 100
WEEKDAY_MAP = {"T2": 0, "T3": 1, "T4": 2, "T5": 3, "T6": 4, "T7": 5, "CN": 6}


# =============================================================================
# 1. HÀM TIỆN ÍCH KIỂM TRA THÔNG TIN HỢP LỆ & ĐỊA ĐIỂM
# =============================================================================

def _to_vn_datetime(d: date, t: dt_time | None = None) -> datetime:
    """Tạo datetime với múi giờ GMT+7."""
    return datetime.combine(d, t or dt_time.min, tzinfo=VN_TZ)


def _is_online_location(loc: Location | None) -> bool:
    """Chỉ coi là Online khi trong thông tin địa điểm có ghi rõ nền tảng trực tuyến."""
    if not loc:
        return False
    text = f"{loc.room or ''} {loc.detail or ''}".lower()
    return "online" in text


# =============================================================================
# 2. CẤU TRÚC DỮ LIỆU NỘI BỘ & ĐẦU RA
# =============================================================================

@dataclass
class _SchedItem:
    task: Task
    start: datetime
    end: datetime
    is_flexible: bool
    estimated_hours: float
    points: int = 0
    category: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass
class ProposedTaskInfo:
    task: Task
    reason: str


@dataclass
class ScheduleResult:
    """Kết quả đầu ra của thuật toán lập lịch."""
    scheduled_tasks: list[Task]
    unselected_tasks: list[ProposedTaskInfo]  # Sự kiện ĐRL hợp lệ nhưng không được chọn (trùng lịch / trần điểm)
    unschedulable_tasks: list[ProposedTaskInfo]  # Task thiếu thông tin bắt buộc, không đủ điều kiện xếp lịch
    total_drl_gained: int
    initial_drl: dict[str, int]
    final_drl: dict[str, int]
    execution_time_seconds: float
    nodes_explored: int

    def print_timetable(self) -> None:
        """In thời khóa biểu tổng hợp trực quan theo ngày và báo cáo chi tiết."""
        print("\n" + "=" * 88)
        print(f"LỊCH BIỂU TỔNG HỢP TUẦN (Tổng ĐRL đạt được: +{self.total_drl_gained}đ)")
        print(f"Điểm theo từng Điều: {self.final_drl}")
        print("=" * 88)

        tasks_with_time: list[tuple[datetime, datetime, Task]] = []
        for t in self.scheduled_tasks:
            if t.start_time and t.start_time.date and t.start_time.time and t.end_time and t.end_time.time:
                st = _to_vn_datetime(t.start_time.date, t.start_time.time)
                et = _to_vn_datetime(t.end_time.date or t.start_time.date, t.end_time.time)
                tasks_with_time.append((st, et, t))

        tasks_with_time.sort(key=lambda x: (x[0], x[1]))
        current_date = None

        if not tasks_with_time:
            print("  (Không có lịch biểu nào được xếp trong tuần này)")
        else:
            for st, et, t in tasks_with_time:
                t_date = st.date()
                if t_date != current_date:
                    current_date = t_date
                    weekday_str = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"][t_date.weekday()]
                    print(f"\n--- {weekday_str}, ngày {t_date.strftime('%d/%m/%Y')} ---")

                tag = f"[{t.type.upper()}]"
                drl_info = f" (+{t.training_points}đ {t.training_point_category})" if t.training_points else ""
                room = t.location.room if (t.location and t.location.room) else ("Online" if _is_online_location(t.location) or t.type == "assignment" else "Chưa rõ phòng")
                time_str = f"{st.strftime('%H:%M')} - {et.strftime('%H:%M')}"
                print(f"  {time_str:<13} {tag:<14} {t.title:<38} | {room}{drl_info}")

        if self.unselected_tasks:
            print("\n" + "-" * 88)
            print("CÁC SỰ KIỆN ĐRL HỢP LỆ NHƯNG KHÔNG ĐƯỢC CHỌN (Do trùng lịch hoặc đã đạt trần điểm):")
            for item in self.unselected_tasks:
                pts = f"+{item.task.training_points}đ" if item.task.training_points else ""
                print(f"  • {item.task.title} ({pts} {item.task.training_point_category or ''}) -> {item.reason}")

        if self.unschedulable_tasks:
            print("\n" + "-" * 88)
            print("DANH SÁCH TASK KHÔNG ĐỦ ĐIỀU KIỆN XẾP LỊCH (Do thiếu thông tin bắt buộc):")
            for item in self.unschedulable_tasks:
                print(f"  • [{item.task.type.upper()}] {item.task.title} -> Lý do: {item.reason}")
        print("=" * 88)


# =============================================================================
# 3. THUẬT TOÁN NHÁNH CẬN (BRANCH AND BOUND SCHEDULER)
# =============================================================================

class BranchAndBoundScheduler:
    def __init__(
        self,
        drl_caps: dict[str, int] | None = None,
        max_total_drl: int = MAX_TOTAL_DRL,
        campus_travel_minutes: int = 60,
    ):
        self.drl_caps = dict(drl_caps or DEFAULT_DRL_CAPS)
        self.max_total_drl = max_total_drl
        self.campus_travel_minutes = campus_travel_minutes

    def schedule(
        self,
        tasks: list[Task],
        initial_drl: dict[str, int] | None = None,
    ) -> ScheduleResult:
        start_time = time.perf_counter()

        # Xác định khoảng tuần lập lịch (Thứ Hai -> Chủ Nhật)
        week_start = datetime.now(VN_TZ).date()
        week_end = week_start + timedelta(days=6)
        week_start_dt = _to_vn_datetime(week_start, datetime.now().time())
        week_end_dt = _to_vn_datetime(week_end, dt_time(23, 59, 59))

        curr_drl = {cat: min(max(0, (initial_drl or {}).get(cat, 0)), cap) for cat, cap in self.drl_caps.items()}
        base_drl = dict(curr_drl)

        # Mỗi lần chạy lại đều tính trạng thái mới từ kết quả hiện tại.
        # Chỉ trạng thái "rejected" do người dùng chủ động hủy mới được giữ nguyên.
        for task in tasks:
            if task.status != "rejected":
                task.status = "proposed"

        # ---------------------------------------------------------------------
        # BƯỚC 1: KIỂM TRA THÔNG TIN HỢP LỆ & PHÂN LOẠI TASK
        # ---------------------------------------------------------------------
        unschedulable_tasks: list[ProposedTaskInfo] = []
        fixed_items: list[_SchedItem] = []
        flexible_workloads: list[_SchedItem] = []
        candidate_items: list[_SchedItem] = []

        for task in tasks:
            # Bỏ qua task bị hủy hoặc là thông báo chung (không phải lịch hoạt động)
            if task.status == "rejected" or task.type == "announcement":
                continue

            # Bỏ qua sự kiện không có điểm rèn luyện và không phải lịch bắt buộc
            # Tuyệt đối không biến sự kiện 0 điểm thành lịch bận cố định!
            points = task.training_points or 0
            if task.type == "event" and points == 0 and not task.compulsory:
                continue

            # -----------------------------------------------------------------
            # 1.1. Xử lý Lịch cố định bắt buộc (Lớp học, Thi cử, Việc riêng bắt buộc)
            # -----------------------------------------------------------------
            if task.type in ("class", "personal") or (task.compulsory and not task.flexible):
                # Lịch học lặp lại theo thứ trong tuần (Recurrence class)
                if task.recurrence:
                    if not task.start_time or not task.start_time.day or not task.start_time.time:
                        unschedulable_tasks.append(ProposedTaskInfo(
                            task=task, reason="Lịch học định kỳ thiếu thứ hoặc giờ bắt đầu"
                        ))
                        continue
                    if not task.end_time or not task.end_time.time:
                        unschedulable_tasks.append(ProposedTaskInfo(
                            task=task, reason="Lịch học định kỳ thiếu giờ kết thúc"
                        ))
                        continue
                    if task.end_time.time <= task.start_time.time:
                        unschedulable_tasks.append(ProposedTaskInfo(
                            task=task, reason="Giờ kết thúc phải sau giờ bắt đầu"
                        ))
                        continue

                    w_idx = WEEKDAY_MAP.get(task.start_time.day)
                    if w_idx is not None:
                        inst_date = week_start + timedelta(days=w_idx)
                        st = _to_vn_datetime(inst_date, task.start_time.time)
                        et = _to_vn_datetime(inst_date, task.end_time.time)
                        overlap = any(not (et <= fix.start or st >= fix.end) for fix in fixed_items)
                        if overlap:
                            unschedulable_tasks.append(ProposedTaskInfo(
                                task=task, reason="Trùng giờ với một lịch cố định khác"
                            ))
                        else:
                            fixed_items.append(_SchedItem(
                                task=task, start=st, end=et, is_flexible=False,
                                estimated_hours=(et - st).total_seconds() / 3600.0
                            ))
                    continue

                # Lịch cố định theo ngày cụ thể
                if not task.start_time or not task.start_time.date or not task.start_time.time:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Lịch cố định thiếu ngày hoặc giờ bắt đầu cụ thể"
                    ))
                    continue
                if not task.end_time or not task.end_time.time:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Lịch cố định thiếu giờ kết thúc cụ thể"
                    ))
                    continue

                st = _to_vn_datetime(task.start_time.date, task.start_time.time)
                et = _to_vn_datetime(task.end_time.date or task.start_time.date, task.end_time.time)
                if et <= st:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Giờ kết thúc phải sau giờ bắt đầu"
                    ))
                    continue

                if et > week_start_dt and st < week_end_dt:
                    overlap = any(not (et <= fix.start or st >= fix.end) for fix in fixed_items)
                    if overlap:
                        unschedulable_tasks.append(ProposedTaskInfo(
                            task=task, reason="Trùng giờ với một lịch cố định khác"
                        ))
                    else:
                        fixed_items.append(_SchedItem(
                            task=task, start=st, end=et, is_flexible=False,
                            estimated_hours=(et - st).total_seconds() / 3600.0
                        ))
                continue

            # -----------------------------------------------------------------
            # 1.2. Xử lý Bài tập / Nhiệm vụ linh hoạt (Assignment)
            # -----------------------------------------------------------------
            if task.type == "assignment" or (task.flexible and points == 0):
                deadline = task.deadline
                if not deadline:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Bài tập thiếu hạn chót (deadline)"
                    ))
                    continue
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=VN_TZ)

                # Cửa sổ làm bài tập: trong tuần này và trước deadline
                w_end = min(deadline, week_end_dt)
                w_start = week_start_dt
                if task.start_time and task.start_time.date:
                    st_cand = _to_vn_datetime(task.start_time.date, task.start_time.time)
                    if st_cand > w_start:
                        w_start = st_cand

                if not task.estimated_hours or task.estimated_hours <= 0:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Thiếu thời lượng ước tính (estimated_hours)"
                    ))
                    continue

                est_h = task.estimated_hours
                if w_end > week_start_dt and w_start < w_end:
                    flexible_workloads.append(_SchedItem(
                        task=task, start=w_start, end=w_end, is_flexible=True,
                        estimated_hours=est_h, window_start=w_start, window_end=w_end
                    ))
                continue

            # -----------------------------------------------------------------
            # 1.3. Xử lý Sự kiện ĐRL ứng viên (Event có training_points > 0)
            # -----------------------------------------------------------------
            if points > 0:
                cat = task.training_point_category
                if cat not in self.drl_caps:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason=f"Danh mục ĐRL không hợp lệ: {cat}"
                    ))
                    continue

                # Nhận diện sự kiện linh hoạt (ví dụ: khảo sát online, bài test trực tuyến mở trong một khoảng thời gian)
                is_flex = task.flexible or (
                    task.deadline is not None and task.start_time and task.start_time.time is None
                )

                if is_flex:
                    dl = task.deadline or (
                        _to_vn_datetime(task.end_time.date, dt_time(23, 59)) if (task.end_time and task.end_time.date) else week_end_dt
                    )
                    if dl.tzinfo is None:
                        dl = dl.replace(tzinfo=VN_TZ)
                    w_start = _to_vn_datetime(task.start_time.date) if (task.start_time and task.start_time.date) else week_start_dt
                    w_start = max(week_start_dt, w_start)
                    w_end = min(dl, week_end_dt)

                    if not task.estimated_hours or task.estimated_hours <= 0:
                        unschedulable_tasks.append(ProposedTaskInfo(
                            task=task, reason="Thiếu thời lượng ước tính (estimated_hours)"
                        ))
                        continue

                    est_h = task.estimated_hours
                    if w_end > week_start_dt and w_start < w_end:
                        candidate_items.append(_SchedItem(
                            task=task, start=w_start, end=w_end, is_flexible=True,
                            estimated_hours=est_h, points=points, category=cat,
                            window_start=w_start, window_end=w_end
                        ))
                    continue

                # Sự kiện cố định trực tiếp
                if not task.start_time or not task.start_time.date or not task.start_time.time:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Sự kiện ĐRL cố định thiếu ngày hoặc giờ bắt đầu cụ thể"
                    ))
                    continue
                if not task.end_time or not task.end_time.time:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Sự kiện ĐRL cố định thiếu giờ kết thúc cụ thể"
                    ))
                    continue

                st_d = task.start_time.date
                et_d = task.end_time.date or st_d
                # Kiểm tra phi lý: sự kiện kéo dài nhiều ngày (multi-day) nhưng ghi cố định
                if et_d > st_d:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason=f"Sự kiện kéo dài nhiều ngày ({st_d} -> {et_d}) không phải một ca cố định"
                    ))
                    continue

                st = _to_vn_datetime(st_d, task.start_time.time)
                et = _to_vn_datetime(et_d, task.end_time.time)
                if et <= st:
                    unschedulable_tasks.append(ProposedTaskInfo(
                        task=task, reason="Giờ kết thúc phải sau giờ bắt đầu"
                    ))
                    continue

                # Chỉ xếp nếu sự kiện diễn ra trong tuần lập lịch
                if et > week_start_dt and st < week_end_dt:
                    candidate_items.append(_SchedItem(
                        task=task, start=st, end=et, is_flexible=False,
                        estimated_hours=(et - st).total_seconds() / 3600.0,
                        points=points, category=cat
                    ))
                continue

        # ---------------------------------------------------------------------
        # BƯỚC 2: LỌC TÍNH KHẢ THI SƠ BỘ VỚI LỊCH CỐ ĐỊNH
        # ---------------------------------------------------------------------
        feasible_candidates: list[_SchedItem] = []
        unselected_tasks: list[ProposedTaskInfo] = []

        for cand in candidate_items:
            if cand.is_flexible:
                feasible_candidates.append(cand)
                continue

            conflict_reason: str | None = None
            for fix in fixed_items:
                # Kiểm tra giao khoảng thời gian
                if not (cand.end <= fix.start or cand.start >= fix.end):
                    conflict_reason = f"Trùng giờ với môn '{fix.task.title}' ({fix.start.strftime('%H:%M')} - {fix.end.strftime('%H:%M')})"
                    break

            if conflict_reason:
                unselected_tasks.append(ProposedTaskInfo(task=cand.task, reason=conflict_reason))
            else:
                feasible_candidates.append(cand)

        # ---------------------------------------------------------------------
        # BƯỚC 3: TIỀN XỬ LÝ CHO NHÁNH CẬN (PRECOMPUTE)
        # ---------------------------------------------------------------------
        feasible_candidates.sort(key=lambda x: (x.is_flexible, x.start, x.end))
        n_cand = len(feasible_candidates)
        categories = sorted(self.drl_caps.keys())

        # Mảng next_compatible: chỉ số sự kiện tiếp theo không xung đột thời gian
        next_compatible = [n_cand] * n_cand
        for i in range(n_cand):
            if feasible_candidates[i].is_flexible:
                next_compatible[i] = i + 1
                continue
            for j in range(i + 1, n_cand):
                if feasible_candidates[j].is_flexible:
                    next_compatible[i] = j
                    break
                if feasible_candidates[j].start >= feasible_candidates[i].end:
                    next_compatible[i] = j
                    break

        # Mảng remaining_by_cat: tổng điểm còn lại của từng danh mục từ vị trí i đến cuối
        remaining_by_cat: dict[str, list[int]] = {cat: [0] * (n_cand + 1) for cat in categories}
        for i in range(n_cand - 1, -1, -1):
            c_cat = feasible_candidates[i].category
            c_pts = feasible_candidates[i].points
            for cat in categories:
                remaining_by_cat[cat][i] = remaining_by_cat[cat][i + 1]
            if c_cat in remaining_by_cat:
                remaining_by_cat[c_cat][i] += c_pts

        # Hàm kiểm tra quỹ thời gian trống cho bài tập linh hoạt
        def is_workload_feasible(selected: list[_SchedItem]) -> bool:
            selected_fixed = [ev for ev in selected if not ev.is_flexible]
            for i, ev in enumerate(selected_fixed):
                for fix in fixed_items:
                    if not (ev.end <= fix.start or ev.start >= fix.end):
                        return False
                for other in selected_fixed[i + 1:]:
                    if not (ev.end <= other.start or ev.start >= other.end):
                        return False

            active_flex = flexible_workloads + [ev for ev in selected if ev.is_flexible]
            if not active_flex:
                return True

            for wl in active_flex:
                total_hours = max(0.0, (wl.end - wl.start).total_seconds() / 3600.0)
                needed_hours = sum(
                    o.estimated_hours for o in active_flex if not (o.end <= wl.start or o.start >= wl.end)
                )
                busy_hours = 0.0
                for fix in fixed_items:
                    overlap = min(wl.end, fix.end) - max(wl.start, fix.start)
                    if overlap.total_seconds() > 0:
                        busy_hours += overlap.total_seconds() / 3600.0

                for ev in selected:
                    if ev.is_flexible:
                        continue
                    overlap = min(wl.end, ev.end) - max(wl.start, ev.start)
                    if overlap.total_seconds() > 0:
                        busy_hours += overlap.total_seconds() / 3600.0

                if total_hours - busy_hours < needed_hours:
                    return False
            return True

        # ---------------------------------------------------------------------
        # BƯỚC 4: GREEDY WARM START & NHÁNH CẬN (BRANCH AND BOUND)
        # ---------------------------------------------------------------------
        best_score = 0
        best_selection: list[tuple[_SchedItem, int]] = []
        greedy_pts = dict(curr_drl)

        for ev in feasible_candidates:
            cand_items = [item for item, _ in best_selection] + [ev]
            if not is_workload_feasible(cand_items):
                continue

            gap = min(self.drl_caps[ev.category] - greedy_pts[ev.category], self.max_total_drl - sum(greedy_pts.values()))
            gain = min(ev.points, gap)
            if gain > 0:
                greedy_pts[ev.category] += gain
                best_score += gain
                best_selection.append((ev, gain))
                if sum(greedy_pts.values()) >= self.max_total_drl:
                    break

        nodes_explored = 0
        best_duration = sum((ev.end - ev.start).total_seconds() for ev, _ in best_selection)

        def search(idx: int, current_selected: list[tuple[_SchedItem, int]], current_pts: dict[str, int], score: int):
            nonlocal best_score, best_selection, best_duration, nodes_explored
            nodes_explored += 1

            dur = sum((ev.end - ev.start).total_seconds() for ev, _ in current_selected)
            if score > best_score or (score == best_score and dur < best_duration):
                best_score = score
                best_selection = list(current_selected)
                best_duration = dur

            if sum(current_pts.values()) >= self.max_total_drl or idx >= n_cand:
                return

            # Cận trên (Upper Bound Bounding)
            potential = sum(min(self.drl_caps[c] - current_pts[c], remaining_by_cat[c][idx]) for c in categories)
            potential = min(potential, self.max_total_drl - sum(current_pts.values()))
            if score + potential <= best_score:
                return  # Cắt tỉa nhánh

            for i in range(idx, n_cand):
                quick_pot = sum(min(self.drl_caps[c] - current_pts[c], remaining_by_cat[c][i]) for c in categories)
                quick_pot = min(quick_pot, self.max_total_drl - sum(current_pts.values()))
                if score + quick_pot <= best_score:
                    break

                ev = feasible_candidates[i]
                gap = min(self.drl_caps[ev.category] - current_pts[ev.category], self.max_total_drl - sum(current_pts.values()))
                gain = min(ev.points, gap)
                if gain <= 0:
                    continue

                cand_items = [item for item, _ in current_selected] + [ev]
                if not is_workload_feasible(cand_items):
                    continue

                new_pts = dict(current_pts)
                new_pts[ev.category] += gain
                search(next_compatible[i], current_selected + [(ev, gain)], new_pts, score + gain)

        search(0, [], curr_drl, 0)

        # ---------------------------------------------------------------------
        # BƯỚC 5: PHÂN BỔ KHUNG GIỜ HỌC TẬP HỢP LÝ CHO CÁC TASK LINH HOẠT
        # ---------------------------------------------------------------------
        occupied_slots: list[tuple[datetime, datetime]] = [
            (f.start, f.end) for f in fixed_items
        ] + [(ev.start, ev.end) for ev, _ in best_selection if not ev.is_flexible]
        occupied_slots.sort()

        def allocate_slot(w_start: datetime, w_end: datetime, dur_hours: float) -> tuple[datetime, datetime] | None:
            """
            Phân bổ khe thời gian học tập ban ngày hợp lý (08:00 - 21:00) trước hạn chót w_end.
            Tuyệt đối không xếp học đêm xuyên qua ngày hôm sau!
            """
            dur = timedelta(hours=max(0.5, dur_hours))
            cursor_day = w_start.date()
            end_day = w_end.date()

            while cursor_day <= end_day:
                day_start = max(w_start, _to_vn_datetime(cursor_day, dt_time(8, 0)))
                # Khung giờ kết thúc tối đa là 21:00 và không vượt quá w_end
                day_end = min(w_end, _to_vn_datetime(cursor_day, dt_time(21, 0)))
                if day_start + dur <= day_end:
                    cursor = day_start
                    while cursor + dur <= day_end:
                        conflict = any(not (cursor + dur <= o_st or cursor >= o_et) for o_st, o_et in occupied_slots)
                        if not conflict:
                            occupied_slots.append((cursor, cursor + dur))
                            occupied_slots.sort()
                            return cursor, cursor + dur
                        cursor += timedelta(minutes=30)
                cursor_day += timedelta(days=1)
            return None

        # Tổng hợp danh sách Task đã lên lịch
        scheduled_tasks: list[Task] = []
        for f in fixed_items:
            f.task.status = "scheduled"
            if f.task.recurrence:
                f.task.start_time = DateDayTime(date=f.start.date(), time=f.start.time())
                f.task.end_time = DateDayTime(date=f.end.date(), time=f.end.time())
            scheduled_tasks.append(f.task)

        # Phân bổ slot cho Assignment
        for wl in flexible_workloads:
            slot = allocate_slot(wl.start, wl.end, wl.estimated_hours)
            if slot is not None:
                st, et = slot
                wl.task.start_time = DateDayTime(date=st.date(), time=st.time())
                wl.task.end_time = DateDayTime(date=et.date(), time=et.time())
                wl.task.status = "scheduled"
                scheduled_tasks.append(wl.task)
            else:
                unschedulable_tasks.append(ProposedTaskInfo(
                    task=wl.task, reason="Không tìm thấy khung giờ rảnh phù hợp (08:00 - 21:00) trước hạn chót"
                ))

        # Phân bổ slot cho các sự kiện ĐRL được chọn
        selected_ev_tasks = set()
        for ev, gain in best_selection:
            if ev.is_flexible:
                slot = allocate_slot(ev.start, ev.end, ev.estimated_hours)
                if slot is not None:
                    st, et = slot
                    ev.task.start_time = DateDayTime(date=st.date(), time=st.time())
                    ev.task.end_time = DateDayTime(date=et.date(), time=et.time())
                    ev.task.status = "scheduled"
                    curr_drl[ev.category] += gain
                    scheduled_tasks.append(ev.task)
                    selected_ev_tasks.add(id(ev.task))
                else:
                    unselected_tasks.append(ProposedTaskInfo(
                        task=ev.task, reason="Không tìm thấy khung giờ rảnh ban ngày (08:00 - 21:00) phù hợp"
                    ))
            else:
                ev.task.status = "scheduled"
                curr_drl[ev.category] += gain
                scheduled_tasks.append(ev.task)
                selected_ev_tasks.add(id(ev.task))

        # Những sự kiện khả thi nhưng không được chọn trong quá trình tối ưu B&B
        for cand in feasible_candidates:
            if id(cand.task) not in selected_ev_tasks:
                if curr_drl.get(cand.category, 0) >= self.drl_caps[cand.category]:
                    r_msg = f"Đã đạt trần tối đa {self.drl_caps[cand.category]}đ của {cand.category}"
                else:
                    r_msg = "Trùng giờ hoặc nhường chỗ cho sự kiện có lợi hơn về điểm/thời lượng"
                unselected_tasks.append(ProposedTaskInfo(task=cand.task, reason=r_msg))

        exec_time = time.perf_counter() - start_time
        return ScheduleResult(
            scheduled_tasks=scheduled_tasks,
            unselected_tasks=unselected_tasks,
            unschedulable_tasks=unschedulable_tasks,
            total_drl_gained=sum(curr_drl[c] - base_drl[c] for c in categories),
            initial_drl=base_drl,
            final_drl=curr_drl,
            execution_time_seconds=exec_time,
            nodes_explored=nodes_explored,
        )
