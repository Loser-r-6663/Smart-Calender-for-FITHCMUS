from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Tái xuất (re-export) các thực thể dữ liệu và hàm tiện ích từ branch_and_bound_models
from .branch_and_bound_models import (
    DEFAULT_DRL_CAPS,
    MAX_TOTAL_DRL,
    DRL_CATEGORY_NAMES,
    DRL_CATEGORY_FULL_NAMES,
    DRL_CATEGORY_CRITERIA,
    FIXED_TASK_TYPES,
    BranchAndBoundResult,
    ScheduledDRLEvent,
    get_travel_buffer_minutes,
    normalize_location,
    parse_timestamp,
)


class BranchAndBoundScheduler:
    """
    Bộ lập lịch tối ưu Điểm Rèn Luyện sử dụng Thuật toán Nhánh Cận (Branch and Bound).
    
    Đặc điểm:
    - Nhận danh sách task trực tiếp từ Database (PostgreSQL tasks table).
    - Tự động tách: Lịch học tập/cố định vs Sự kiện ĐRL.
    - Cắt tỉa thông minh theo 3 tiêu chí:
      1. Xung đột thời gian & Thời gian di chuyển cơ sở (CS1 <-> CS2).
      2. Trần điểm 5 Điều (Category Cap Pruning).
      3. Cận trên lý thuyết (Upper Bound Pruning).
    """

    def __init__(
        self,
        drl_caps: Optional[Dict[str, int]] = None,
        campus_travel_minutes: int = 60,
        global_cap: Optional[int] = MAX_TOTAL_DRL,
    ):
        self.drl_caps = dict(drl_caps or DEFAULT_DRL_CAPS)
        self.campus_travel_minutes = campus_travel_minutes
        self.global_cap = global_cap

    def schedule(
        self,
        tasks: List[Any],
        initial_drl: Optional[Dict[str, int]] = None,
    ) -> BranchAndBoundResult:
        """
        Thực thi lập lịch Branch & Bound.
        
        Args:
            tasks: Danh sách các task lấy từ Database (dạng dict hoặc Pydantic object TaskData/Task).
            initial_drl: Điểm ĐRL hiện có theo 5 Điều (ví dụ: {'dieu_1': 27, 'dieu_2': 12, ...}).
        """
        start_exec_time = time.perf_counter()

        # Chuẩn hóa initial_drl
        curr_drl: Dict[str, int] = {cat: 0 for cat in self.drl_caps}
        if initial_drl:
            for cat, pts in initial_drl.items():
                if cat in curr_drl:
                    curr_drl[cat] = min(max(0, int(pts)), self.drl_caps[cat])

        init_total = sum(curr_drl.values())
        if self.global_cap is not None and init_total >= self.global_cap:
            exec_duration = time.perf_counter() - start_exec_time
            return BranchAndBoundResult(
                status="OPTIMAL",
                selected_events=[],
                total_drl_gained=0,
                initial_drl=curr_drl,
                final_drl=curr_drl,
                drl_caps=self.drl_caps,
                execution_time_seconds=exec_duration,
                nodes_explored=0,
                total_candidates_considered=0,
                global_cap=self.global_cap,
            )

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 1: TÁCH LỊCH HỌC CỐ ĐỊNH & SỰ KIỆN ĐRL ỨNG VIÊN
        # ---------------------------------------------------------------------
        fixed_intervals: List[Tuple[datetime, datetime, str, str]] = []
        raw_candidates: List[Dict[str, Any]] = []

        for item in tasks:
            task_dict: Dict[str, Any] = item if isinstance(item, dict) else item.__dict__
            
            task_id = str(task_dict.get("id", ""))
            title = str(task_dict.get("title", "Không tên"))
            task_type = str(task_dict.get("type", "")).lower()
            status = str(task_dict.get("status", "active")).lower()
            loc_raw = task_dict.get("location")
            location = normalize_location(loc_raw)
            t_points = int(task_dict.get("training_points") or 0)
            drl_cat = task_dict.get("drl_category")
            if drl_cat:
                drl_cat = str(drl_cat).lower()

            st = parse_timestamp(task_dict.get("start_time"))
            et = parse_timestamp(task_dict.get("end_time"))
            dl = parse_timestamp(task_dict.get("deadline"))

            if status in {"archived", "cancelled"}:
                continue

            # Sự kiện online chỉ có hạn chót deadline mà có ĐRL
            if st is None and et is None and dl is not None and t_points > 0:
                st = dl - timedelta(minutes=30)
                et = dl

            if st is None or et is None or st >= et:
                continue

            # Phân loại
            if task_type in FIXED_TASK_TYPES or t_points == 0:
                fixed_intervals.append((st, et, location, title))
            elif t_points > 0:
                if drl_cat not in self.drl_caps:
                    drl_cat = "dieu_3"
                raw_candidates.append({
                    "id": task_id,
                    "title": title,
                    "start_time": st,
                    "end_time": et,
                    "location": location,
                    "training_points": t_points,
                    "drl_category": drl_cat,
                })

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 2: LỌC SƠ BỘ KHẢ THI (FEASIBILITY FILTERING)
        # ---------------------------------------------------------------------
        feasible_events: List[Dict[str, Any]] = []

        for cand in raw_candidates:
            c_st, c_et, c_loc = cand["start_time"], cand["end_time"], cand["location"]
            is_conflict = False

            for f_st, f_et, f_loc, _ in fixed_intervals:
                # 1. Trùng giờ trực tiếp
                if not (c_et <= f_st or c_st >= f_et):
                    is_conflict = True
                    break

                # 2. Xung đột di chuyển trước giờ học
                if c_et <= f_st:
                    travel_need = get_travel_buffer_minutes(c_loc, f_loc, self.campus_travel_minutes)
                    if c_et + timedelta(minutes=travel_need) > f_st:
                        is_conflict = True
                        break

                # 3. Xung đột di chuyển sau giờ học
                if c_st >= f_et:
                    travel_need = get_travel_buffer_minutes(f_loc, c_loc, self.campus_travel_minutes)
                    if f_et + timedelta(minutes=travel_need) > c_st:
                        is_conflict = True
                        break

            if not is_conflict:
                feasible_events.append(cand)

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 3: THUẬT TOÁN NHÁNH CẬN (BRANCH AND BOUND)
        # ---------------------------------------------------------------------
        # Sắp xếp các sự kiện theo thời gian bắt đầu
        feasible_events.sort(key=lambda x: (x["start_time"], x["end_time"]))
        total_candidates = len(feasible_events)

        if total_candidates == 0:
            exec_duration = time.perf_counter() - start_exec_time
            return BranchAndBoundResult(
                status="FEASIBLE",
                selected_events=[],
                total_drl_gained=0,
                initial_drl=curr_drl,
                final_drl=curr_drl,
                drl_caps=self.drl_caps,
                execution_time_seconds=exec_duration,
                nodes_explored=0,
                total_candidates_considered=0,
            )

        cat_list = tuple(sorted(self.drl_caps.keys()))

        # TÍNH TRƯỚC BƯỚC NHẢY (PRECOMPUTE NEXT COMPATIBLE EVENT)
        # precomputed_next[i] = chỉ số sự kiện j nhỏ nhất (j > i) không xung đột với sự kiện i
        precomputed_next: List[int] = [total_candidates] * total_candidates
        for i in range(total_candidates):
            ev_i = feasible_events[i]
            for j in range(i + 1, total_candidates):
                ev_j = feasible_events[j]
                tr = get_travel_buffer_minutes(ev_i["location"], ev_j["location"], self.campus_travel_minutes)
                if ev_j["start_time"] >= ev_i["end_time"] + timedelta(minutes=tr):
                    precomputed_next[i] = j
                    break

        # Mảng tính trước điểm tối đa còn lại của từng Điều từ vị trí i đến hết
        remaining_by_cat: Dict[str, List[int]] = {cat: [0] * (total_candidates + 1) for cat in cat_list}
        for i in range(total_candidates - 1, -1, -1):
            ev = feasible_events[i]
            for cat in cat_list:
                remaining_by_cat[cat][i] = remaining_by_cat[cat][i + 1]
            remaining_by_cat[ev["drl_category"]][i] += ev["training_points"]

        # 1. GREEDY WARM START: Tìm nghiệm khởi đầu nhanh để thiết lập cận dưới cao
        best_score = 0
        best_selection: List[Tuple[Dict[str, Any], int]] = []
        greedy_pts = dict(curr_drl)
        last_end_greedy: Optional[datetime] = None
        last_loc_greedy: str = "ONLINE"

        for ev in feasible_events:
            tr = get_travel_buffer_minutes(last_loc_greedy, ev["location"], self.campus_travel_minutes) if last_end_greedy else 0
            if last_end_greedy is None or ev["start_time"] >= last_end_greedy + timedelta(minutes=tr):
                cat = ev["drl_category"]
                cat_gap = self.drl_caps[cat] - greedy_pts[cat]
                if self.global_cap is not None:
                    global_gap = self.global_cap - sum(greedy_pts.values())
                    effective_gap = min(cat_gap, global_gap)
                else:
                    effective_gap = cat_gap

                gain = min(ev["training_points"], effective_gap)
                if gain > 0:
                    greedy_pts[cat] += gain
                    best_score += gain
                    best_selection.append((ev, gain))
                    last_end_greedy = ev["end_time"]
                    last_loc_greedy = ev["location"]
                    if self.global_cap is not None and sum(greedy_pts.values()) >= self.global_cap:
                        break

        nodes_count = 0
        best_duration = sum((ev["end_time"] - ev["start_time"]).total_seconds() for ev, _ in best_selection)

        # 2. HÀM TÌM KIẾM NHÁNH CẬN VỚI BƯỚC NHẢY ĐÃ TÍNH TRƯỚC (PRECOMPUTED JUMP)
        def search(
            current_idx: int,
            current_selected: List[Tuple[Dict[str, Any], int]],
            current_points: Dict[str, int],
            score: int,
        ) -> None:
            nonlocal best_score, best_selection, best_duration, nodes_count
            nodes_count += 1

            current_duration = sum((ev["end_time"] - ev["start_time"]).total_seconds() for ev, _ in current_selected)
            if score > best_score or (score == best_score and current_duration < best_duration):
                best_score = score
                best_selection = list(current_selected)
                best_duration = current_duration

            # Cắt tỉa chạm trần toàn cục (Global Cap Pruning): Đã đạt trần thì không cần duyệt sâu thêm
            if self.global_cap is not None and sum(current_points.values()) >= self.global_cap:
                return

            if current_idx >= total_candidates:
                return

            # Cắt tỉa theo Cận trên (Upper Bound Pruning)
            potential = 0
            for cat in cat_list:
                gap = self.drl_caps[cat] - current_points[cat]
                if gap > 0:
                    potential += min(gap, remaining_by_cat[cat][current_idx])
            if self.global_cap is not None:
                potential = min(potential, self.global_cap - sum(current_points.values()))

            if score + potential <= best_score:
                return

            # Duyệt các ứng viên tiếp theo có thể chọn
            for i in range(current_idx, total_candidates):
                # Cận trên cục bộ từ vị trí i
                quick_pot = 0
                for cat in cat_list:
                    gap = self.drl_caps[cat] - current_points[cat]
                    if gap > 0:
                        quick_pot += min(gap, remaining_by_cat[cat][i])
                if self.global_cap is not None:
                    quick_pot = min(quick_pot, self.global_cap - sum(current_points.values()))

                if score + quick_pot <= best_score:
                    break  # Vì i tăng dần, remaining points chỉ có thể giảm

                ev = feasible_events[i]
                cat = ev["drl_category"]
                cat_gap = self.drl_caps[cat] - current_points[cat]
                if self.global_cap is not None:
                    cat_gap = min(cat_gap, self.global_cap - sum(current_points.values()))

                gain = min(ev["training_points"], cat_gap)
                if gain <= 0:
                    continue

                # Nhảy cóc O(1) đến sự kiện tiếp theo không xung đột
                next_k = precomputed_next[i]
                new_pts = dict(current_points)
                new_pts[cat] += gain
                search(next_k, current_selected + [(ev, gain)], new_pts, score + gain)

        # Bắt đầu tìm kiếm từ sự kiện 0
        search(0, [], curr_drl, 0)

        exec_duration = time.perf_counter() - start_exec_time

        # Chuẩn bị danh sách sự kiện trả về
        final_events: List[ScheduledDRLEvent] = []
        final_drl: Dict[str, int] = dict(curr_drl)

        for ev_data, pts_gain in best_selection:
            final_drl[ev_data["drl_category"]] += pts_gain
            final_events.append(ScheduledDRLEvent(
                task_id=ev_data["id"],
                title=ev_data["title"],
                start_time=ev_data["start_time"],
                end_time=ev_data["end_time"],
                location=ev_data["location"],
                training_points=ev_data["training_points"],
                drl_category=ev_data["drl_category"],
                points_gained=pts_gain,
            ))

        return BranchAndBoundResult(
            status="OPTIMAL",
            selected_events=final_events,
            total_drl_gained=best_score,
            initial_drl=curr_drl,
            final_drl=final_drl,
            drl_caps=self.drl_caps,
            execution_time_seconds=exec_duration,
            nodes_explored=nodes_count,
            total_candidates_considered=total_candidates,
            global_cap=self.global_cap,
        )


__all__ = [
    "BranchAndBoundScheduler",
    "BranchAndBoundResult",
    "ScheduledDRLEvent",
    "DEFAULT_DRL_CAPS",
    "MAX_TOTAL_DRL",
    "DRL_CATEGORY_NAMES",
    "DRL_CATEGORY_FULL_NAMES",
    "DRL_CATEGORY_CRITERIA",
    "FIXED_TASK_TYPES",
    "get_travel_buffer_minutes",
    "normalize_location",
    "parse_timestamp",
]
