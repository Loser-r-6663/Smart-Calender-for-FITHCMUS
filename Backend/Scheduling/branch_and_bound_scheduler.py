from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .branch_and_bound_models import (
    DEFAULT_DRL_CAPS,
    MAX_TOTAL_DRL,
    DRL_CATEGORY_NAMES,
    DRL_CATEGORY_FULL_NAMES,
    DRL_CATEGORY_CRITERIA,
    FIXED_TASK_TYPES,
    BranchAndBoundResult,
    ScheduledDRLEvent,
    format_location_text,
    get_travel_buffer_minutes,
    max_travel_buffer_minutes,
    normalize_drl_category,
    normalize_location,
    parse_timestamp,
    parse_travel_buffer_value,
)


class BranchAndBoundScheduler:
    """
    Bộ lập lịch tối ưu Điểm Rèn Luyện sử dụng Thuật toán Nhánh Cận (Branch and Bound).
    Tương thích trực tiếp với ExtractedTask trên nhánh Crawler cũng như dict/TaskObject.
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
        start_exec_time = time.perf_counter()

        # Chuẩn hóa initial_drl (hỗ trợ cả key 'dieu_1..5' và 'Articles 1..5')
        curr_drl: Dict[str, int] = {cat: 0 for cat in self.drl_caps}
        if initial_drl:
            for cat, pts in initial_drl.items():
                norm_cat = normalize_drl_category(cat)
                if norm_cat in curr_drl:
                    curr_drl[norm_cat] = min(max(0, int(pts)), self.drl_caps[norm_cat])
        base_initial_drl: Dict[str, int] = dict(curr_drl)

        init_total = sum(curr_drl.values())
        if self.global_cap is not None and init_total >= self.global_cap:
            exec_duration = time.perf_counter() - start_exec_time
            return BranchAndBoundResult(
                status="OPTIMAL",
                selected_events=[],
                total_drl_gained=0,
                initial_drl=base_initial_drl,
                final_drl=curr_drl,
                drl_caps=self.drl_caps,
                execution_time_seconds=exec_duration,
                nodes_explored=0,
                total_candidates_considered=0,
                global_cap=self.global_cap,
            )

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 1: TÁCH LỊCH HỌC CỐ ĐỊNH, NHIỆM VỤ LINH HOẠT & SỰ KIỆN ĐRL ỨNG VIÊN
        # ---------------------------------------------------------------------
        fixed_intervals: List[Tuple[datetime, datetime, str, str, Optional[int]]] = []
        fixed_tasks_summary: List[Dict[str, Any]] = []
        raw_candidates: List[Dict[str, Any]] = []
        flexible_workloads: List[Dict[str, Any]] = []
        pinned_scheduled_events: List[ScheduledDRLEvent] = []
        pinned_drl_gained = 0

        for item in tasks:
            if isinstance(item, dict):
                task_dict: Dict[str, Any] = dict(item)
            elif hasattr(item, "model_dump"):
                task_dict = item.model_dump()
                task_dict["location"] = getattr(item, "location", task_dict.get("location"))
                task_dict["start_time"] = getattr(item, "start_time", task_dict.get("start_time"))
                task_dict["end_time"] = getattr(item, "end_time", task_dict.get("end_time"))
            else:
                task_dict = dict(item.__dict__)

            pin_status = str(task_dict.get("pin_status") or "default").lower()
            if pin_status == "rejected":
                continue
            is_pinned = bool(task_dict.get("is_pinned")) or pin_status == "pinned"
            has_custom_time = bool(task_dict.get("_has_custom_time"))

            raw_travel_buf = task_dict.get("travel_buffer_minutes")
            travel_buf = parse_travel_buffer_value(raw_travel_buf)

            task_id = str(task_dict.get("id") or "")
            title = str(task_dict.get("title") or "Không tên")
            task_type = str(task_dict.get("type") or "").lower()
            status = str(task_dict.get("status") or "active").lower()

            loc_raw = task_dict.get("location")
            loc_text = format_location_text(loc_raw)
            if task_type in {"class", "exam"}:
                if not loc_text:
                    loc_text = "Cơ sở 1"
                elif (
                    "cơ sở 1" not in loc_text.lower()
                    and "cs1" not in loc_text.lower()
                    and "cơ sở 2" not in loc_text.lower()
                    and "cs2" not in loc_text.lower()
                    and "linh trung" not in loc_text.lower()
                    and "thủ đức" not in loc_text.lower()
                ):
                    loc_text = f"{loc_text}, Cơ sở 1"
                task_dict["location"] = loc_text
            location = normalize_location(
                loc_text or loc_raw,
                default="CS1" if task_type in {"class", "exam"} else "ONLINE",
                has_custom_travel_buffer=(max_travel_buffer_minutes(travel_buf) > 0),
            )

            t_points = int(task_dict.get("training_points") or 0)
            drl_cat = normalize_drl_category(
                task_dict.get("drl_category") or task_dict.get("training_point_category")
            )

            st = parse_timestamp(task_dict.get("start_time"))
            et = parse_timestamp(task_dict.get("end_time"))
            dl = parse_timestamp(task_dict.get("deadline"))
            orig_win_st = parse_timestamp(task_dict.get("_original_window_start")) or st
            orig_win_et = parse_timestamp(task_dict.get("_original_window_end")) or dl or et

            if status in {"archived", "cancelled", "done"}:
                continue

            # Sự kiện có start_time nhưng thiếu end_time -> dùng estimated_hours (mặc định 2.0h)
            if st is not None and et is None and dl is None:
                est_dur = float(task_dict.get("estimated_hours") or 2.0)
                et = st + timedelta(hours=est_dur)

            # Sự kiện online chỉ có hạn chót deadline mà có ĐRL
            if st is None and et is None and dl is not None and t_points > 0:
                dur_h = float(task_dict.get("estimated_hours") or 0.5)
                st = dl - timedelta(hours=dur_h)
                et = dl

            # Nếu end_time thiếu nhưng có deadline
            if et is None and dl is not None:
                et = dl

            # Assignment chỉ có deadline mà thiếu start_time
            if st is None and et is not None and task_type == "assignment":
                st = et - timedelta(hours=24)

            if st is None or et is None or st >= et:
                continue

            # Nhận diện task có thời gian làm linh hoạt:
            # Chênh lệch giữa end/deadline và start >= 3.5h đối với assignment hoặc event online
            # (Nếu user đã chủ động gán custom_start_time / custom_end_time cụ thể thì khóa cứng vào khung giờ đó)
            is_online = location == "ONLINE" or "online" in loc_text.lower()
            effective_end = et if has_custom_time else (dl or et)
            window_delta_hours = (effective_end - st).total_seconds() / 3600.0
            is_flexible_task = False
            est_h = 0.5

            if not has_custom_time and window_delta_hours >= 3.5 and (task_type == "assignment" or is_online):
                is_flexible_task = True
                raw_est = task_dict.get("estimated_hours")
                if raw_est and float(raw_est) > 0:
                    est_h = float(raw_est)
                elif task_type == "assignment":
                    est_h = 3.5
                else:
                    est_h = 0.5

                # Task linh hoạt không có điểm ĐRL (assignment/quiz bắt buộc) -> đưa vào flexible_workloads cố định
                if t_points == 0:
                    flexible_workloads.append({
                        "id": task_id,
                        "title": title,
                        "type": task_type or "assignment",
                        "start_time": st,
                        "end_time": effective_end,
                        "estimated_hours": est_h,
                    })
                    continue

            # Phân loại
            if task_type in FIXED_TASK_TYPES or t_points == 0:
                fixed_intervals.append((st, et, location, title, travel_buf))
                fixed_tasks_summary.append({
                    "id": task_id,
                    "title": title,
                    "type": task_type or "personal",
                    "start_time": st,
                    "end_time": et,
                    "location": loc_text or location,
                    "normalized_location": location,
                    "travel_buffer_minutes": travel_buf,
                })
            elif t_points > 0:
                if drl_cat not in self.drl_caps:
                    drl_cat = "dieu_3"
                if is_pinned:
                    if not is_flexible_task:
                        fixed_intervals.append((st, et, location, title, travel_buf))
                    else:
                        flexible_workloads.append({
                            "id": task_id,
                            "title": title,
                            "type": "event",
                            "start_time": st,
                            "end_time": effective_end,
                            "estimated_hours": est_h,
                        })
                    cat_gap = self.drl_caps[drl_cat] - curr_drl[drl_cat]
                    if self.global_cap is not None:
                        cat_gap = min(cat_gap, self.global_cap - sum(curr_drl.values()))
                    gain = min(t_points, max(0, cat_gap))
                    curr_drl[drl_cat] += gain
                    pinned_drl_gained += gain
                    pinned_scheduled_events.append(ScheduledDRLEvent(
                        task_id=task_id,
                        title=title,
                        start_time=st,
                        end_time=effective_end if is_flexible_task else et,
                        location=location,
                        training_points=t_points,
                        drl_category=drl_cat,
                        points_gained=gain,
                        is_flexible=is_flexible_task,
                        window_start=orig_win_st,
                        window_end=orig_win_et,
                        estimated_hours=est_h if is_flexible_task else (et - st).total_seconds() / 3600.0,
                        is_pinned=True,
                        travel_buffer_minutes=travel_buf,
                    ))
                else:
                    raw_candidates.append({
                        "id": task_id,
                        "title": title,
                        "start_time": st,
                        "end_time": effective_end if is_flexible_task else et,
                        "window_start": orig_win_st,
                        "window_end": orig_win_et,
                        "location": location,
                        "training_points": t_points,
                        "drl_category": drl_cat,
                        "is_flexible": is_flexible_task,
                        "estimated_hours": est_h if is_flexible_task else (et - st).total_seconds() / 3600.0,
                        "travel_buffer_minutes": travel_buf,
                    })

        # Hàm kiểm tra quỹ thời gian rảnh đủ để thực hiện các task linh hoạt (cả assignment và event online linh hoạt được chọn)
        def is_workload_feasible(selected_events_list: List[Dict[str, Any]]) -> bool:
            active_flex = list(flexible_workloads) + [
                {
                    "id": ev["id"],
                    "title": ev["title"],
                    "start_time": ev["start_time"],
                    "end_time": ev["end_time"],
                    "estimated_hours": ev["estimated_hours"],
                }
                for ev in selected_events_list
                if ev.get("is_flexible")
            ]
            if not active_flex:
                return True

            for wl in active_flex:
                w_st = wl["start_time"]
                w_et = wl["end_time"]

                total_window_hours = max(0.0, (w_et - w_st).total_seconds() / 3600.0)

                needed_hours = 0.0
                for o_wl in active_flex:
                    if not (o_wl["end_time"] <= w_st or o_wl["start_time"] >= w_et):
                        needed_hours += o_wl["estimated_hours"]

                busy_fixed = 0.0
                for f_st, f_et, _, _, f_buf in fixed_intervals:
                    buf_mins = max_travel_buffer_minutes(f_buf)
                    buf_td = timedelta(minutes=buf_mins) if buf_mins > 0 else timedelta(0)
                    eff_f_st = f_st - buf_td
                    eff_f_et = f_et + buf_td
                    overlap_st = max(w_st, eff_f_st)
                    overlap_et = min(w_et, eff_f_et)
                    if overlap_et > overlap_st:
                        busy_fixed += (overlap_et - overlap_st).total_seconds() / 3600.0

                base_free_hours = total_window_hours - busy_fixed
                slack = max(0.0, base_free_hours - needed_hours)

                busy_drl = 0.0
                for ev in selected_events_list:
                    if ev.get("is_flexible"):
                        continue
                    ev_buf_mins = max_travel_buffer_minutes(ev.get("travel_buffer_minutes"))
                    ev_buf_td = timedelta(minutes=ev_buf_mins) if ev_buf_mins > 0 else timedelta(0)
                    e_st = ev["start_time"] - ev_buf_td
                    e_et = ev["end_time"] + ev_buf_td
                    overlap_st = max(w_st, e_st)
                    overlap_et = min(w_et, e_et)
                    if overlap_et > overlap_st:
                        busy_drl += (overlap_et - overlap_st).total_seconds() / 3600.0

                if busy_drl > slack or base_free_hours < needed_hours:
                    return False

            return True

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 2: LỌC SƠ BỘ KHẢ THI (FEASIBILITY FILTERING) & KHỬ TRÙNG LẶP
        # ---------------------------------------------------------------------
        feasible_events: List[Dict[str, Any]] = []
        seen_candidate_keys: set[tuple[str, datetime, datetime]] = set()

        for cand in raw_candidates:
            dedup_key = (
                " ".join(str(cand["title"]).casefold().split()),
                cand["start_time"],
                cand["end_time"],
            )
            if dedup_key in seen_candidate_keys:
                continue
            seen_candidate_keys.add(dedup_key)

            if cand.get("is_flexible"):
                if is_workload_feasible([cand]):
                    feasible_events.append(cand)
                continue

            c_st, c_et, c_loc = cand["start_time"], cand["end_time"], cand["location"]
            c_buf = cand.get("travel_buffer_minutes")
            is_conflict = False

            for f_st, f_et, f_loc, _, f_buf in fixed_intervals:
                if not (c_et <= f_st or c_st >= f_et):
                    is_conflict = True
                    break

                if c_et <= f_st:
                    travel_need = get_travel_buffer_minutes(
                        c_loc, f_loc, self.campus_travel_minutes, c_buf, f_buf
                    )
                    if c_et + timedelta(minutes=travel_need) > f_st:
                        is_conflict = True
                        break

                if c_st >= f_et:
                    travel_need = get_travel_buffer_minutes(
                        f_loc, c_loc, self.campus_travel_minutes, f_buf, c_buf
                    )
                    if f_et + timedelta(minutes=travel_need) > c_st:
                        is_conflict = True
                        break

            if not is_conflict:
                feasible_events.append(cand)

        # ---------------------------------------------------------------------
        # BÀI TOÁN CON 3: THUẬT TOÁN NHÁNH CẬN (BRANCH AND BOUND)
        # ---------------------------------------------------------------------
        feasible_events.sort(
            key=lambda x: (not bool(x.get("is_flexible")), x["start_time"], x["end_time"])
        )
        total_candidates = len(feasible_events)

        occupied_slots: List[Tuple[datetime, datetime]] = [
            (
                f_st - timedelta(minutes=max_travel_buffer_minutes(f_buf)),
                f_et + timedelta(minutes=max_travel_buffer_minutes(f_buf)),
            )
            for f_st, f_et, _, _, f_buf in fixed_intervals
        ]

        def allocate_flexible_slot(
            w_st: datetime, w_et: datetime, dur_hours: float
        ) -> Tuple[datetime, datetime]:
            dur = timedelta(hours=max(0.25, float(dur_hours or 0.5)))
            if w_st + dur > w_et:
                return w_st, w_et

            def _find_in_bounds(b_st: datetime, b_et: datetime) -> Optional[Tuple[datetime, datetime]]:
                if b_st + dur > b_et:
                    return None
                blockers = sorted(
                    (max(b_st, o_st), min(b_et, o_et))
                    for o_st, o_et in occupied_slots
                    if o_et > b_st and o_st < b_et
                )
                cursor = b_st
                for blk_st, blk_et in blockers:
                    if cursor + dur <= blk_st:
                        return cursor, cursor + dur
                    if blk_et > cursor:
                        cursor = blk_et
                if cursor + dur <= b_et:
                    return cursor, cursor + dur
                return None

            # Ưu tiên xếp vào khung giờ sinh hoạt ban ngày (08:00 -> 22:00) trong từng ngày của cửa sổ
            day_cursor = w_st.date()
            end_date = w_et.date()
            tz = w_st.tzinfo
            while day_cursor <= end_date:
                day_8am = datetime(day_cursor.year, day_cursor.month, day_cursor.day, 8, 0, tzinfo=tz)
                day_10pm = datetime(day_cursor.year, day_cursor.month, day_cursor.day, 22, 0, tzinfo=tz)
                b_st = max(w_st, day_8am)
                b_et = min(w_et, day_10pm)
                found = _find_in_bounds(b_st, b_et)
                if found is not None:
                    occupied_slots.append(found)
                    return found
                day_cursor += timedelta(days=1)

            # Fallback: tìm bất kỳ khe trống nào trong [w_st, w_et]
            found_any = _find_in_bounds(w_st, w_et)
            if found_any is not None:
                occupied_slots.append(found_any)
                return found_any
            return w_st, w_st + dur

        # Cấp phát khung giờ cụ thể cho các sự kiện linh hoạt đã được ghim (nếu có)
        for idx, p_ev in enumerate(pinned_scheduled_events):
            if p_ev.is_flexible:
                p_st, p_et = allocate_flexible_slot(
                    p_ev.start_time, p_ev.end_time, p_ev.estimated_hours
                )
                pinned_scheduled_events[idx] = ScheduledDRLEvent(
                    task_id=p_ev.task_id,
                    title=p_ev.title,
                    start_time=p_st,
                    end_time=p_et,
                    location=p_ev.location,
                    training_points=p_ev.training_points,
                    drl_category=p_ev.drl_category,
                    points_gained=p_ev.points_gained,
                    is_flexible=True,
                    window_start=p_ev.window_start or p_ev.start_time,
                    window_end=p_ev.window_end or p_ev.end_time,
                    estimated_hours=p_ev.estimated_hours,
                    is_pinned=True,
                    travel_buffer_minutes=p_ev.travel_buffer_minutes,
                )

        if total_candidates == 0:
            exec_duration = time.perf_counter() - start_exec_time
            pinned_scheduled_events.sort(key=lambda ev: (ev.start_time, ev.end_time))
            return BranchAndBoundResult(
                status="OPTIMAL" if pinned_scheduled_events else "FEASIBLE",
                selected_events=pinned_scheduled_events,
                total_drl_gained=pinned_drl_gained,
                initial_drl=base_initial_drl,
                final_drl=dict(curr_drl),
                drl_caps=self.drl_caps,
                execution_time_seconds=exec_duration,
                nodes_explored=0,
                total_candidates_considered=0,
                global_cap=self.global_cap,
                unselected_events=[],
                fixed_tasks_summary=fixed_tasks_summary,
                flexible_tasks_summary=list(flexible_workloads),
            )

        cat_list = tuple(sorted(self.drl_caps.keys()))

        precomputed_next: List[int] = [total_candidates] * total_candidates
        for i in range(total_candidates):
            ev_i = feasible_events[i]
            if ev_i.get("is_flexible"):
                precomputed_next[i] = i + 1
                continue
            for j in range(i + 1, total_candidates):
                ev_j = feasible_events[j]
                if ev_j.get("is_flexible"):
                    precomputed_next[i] = j
                    break
                tr = get_travel_buffer_minutes(
                    ev_i["location"],
                    ev_j["location"],
                    self.campus_travel_minutes,
                    ev_i.get("travel_buffer_minutes"),
                    ev_j.get("travel_buffer_minutes"),
                )
                if ev_j["start_time"] >= ev_i["end_time"] + timedelta(minutes=tr):
                    precomputed_next[i] = j
                    break

        remaining_by_cat: Dict[str, List[int]] = {cat: [0] * (total_candidates + 1) for cat in cat_list}
        for i in range(total_candidates - 1, -1, -1):
            ev = feasible_events[i]
            for cat in cat_list:
                remaining_by_cat[cat][i] = remaining_by_cat[cat][i + 1]
            remaining_by_cat[ev["drl_category"]][i] += ev["training_points"]

        # 1. GREEDY WARM START
        best_score = 0
        best_selection: List[Tuple[Dict[str, Any], int]] = []
        greedy_pts = dict(curr_drl)
        last_end_greedy: Optional[datetime] = None
        last_loc_greedy: str = "ONLINE"
        last_buf_greedy: Optional[int] = None

        for ev in feasible_events:
            is_flex = bool(ev.get("is_flexible"))
            tr = (
                0
                if is_flex or not last_end_greedy
                else get_travel_buffer_minutes(
                    last_loc_greedy,
                    ev["location"],
                    self.campus_travel_minutes,
                    last_buf_greedy,
                    ev.get("travel_buffer_minutes"),
                )
            )
            if is_flex or last_end_greedy is None or ev["start_time"] >= last_end_greedy + timedelta(minutes=tr):
                cand_selection = [e for e, _ in best_selection] + [ev]
                if not is_workload_feasible(cand_selection):
                    continue

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
                    if not is_flex:
                        last_end_greedy = ev["end_time"]
                        last_loc_greedy = ev["location"]
                        last_buf_greedy = ev.get("travel_buffer_minutes")
                    if self.global_cap is not None and sum(greedy_pts.values()) >= self.global_cap:
                        break

        nodes_count = 0
        best_duration = sum((ev["end_time"] - ev["start_time"]).total_seconds() for ev, _ in best_selection)

        # 2. HÀM TÌM KIẾM NHÁNH CẬN
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

            if self.global_cap is not None and sum(current_points.values()) >= self.global_cap:
                return

            if current_idx >= total_candidates:
                return

            potential = 0
            for cat in cat_list:
                gap = self.drl_caps[cat] - current_points[cat]
                if gap > 0:
                    potential += min(gap, remaining_by_cat[cat][current_idx])
            if self.global_cap is not None:
                potential = min(potential, self.global_cap - sum(current_points.values()))

            if score + potential <= best_score:
                return

            for i in range(current_idx, total_candidates):
                quick_pot = 0
                for cat in cat_list:
                    gap = self.drl_caps[cat] - current_points[cat]
                    if gap > 0:
                        quick_pot += min(gap, remaining_by_cat[cat][i])
                if self.global_cap is not None:
                    quick_pot = min(quick_pot, self.global_cap - sum(current_points.values()))

                if score + quick_pot <= best_score:
                    break

                ev = feasible_events[i]
                cat = ev["drl_category"]
                cat_gap = self.drl_caps[cat] - current_points[cat]
                if self.global_cap is not None:
                    cat_gap = min(cat_gap, self.global_cap - sum(current_points.values()))

                gain = min(ev["training_points"], cat_gap)
                if gain <= 0:
                    continue

                cand_selection = [e for e, _ in current_selected] + [ev]
                if not is_workload_feasible(cand_selection):
                    continue

                next_k = precomputed_next[i]
                new_pts = dict(current_points)
                new_pts[cat] += gain
                search(next_k, current_selected + [(ev, gain)], new_pts, score + gain)

        search(0, [], curr_drl, 0)

        exec_duration = time.perf_counter() - start_exec_time

        for ev_data, _ in best_selection:
            if not ev_data.get("is_flexible"):
                buf_td = timedelta(minutes=max_travel_buffer_minutes(ev_data.get("travel_buffer_minutes")))
                occupied_slots.append((ev_data["start_time"] - buf_td, ev_data["end_time"] + buf_td))

        final_events: List[ScheduledDRLEvent] = list(pinned_scheduled_events)
        final_drl: Dict[str, int] = dict(curr_drl)
        selected_ids_set = {id(ev_data) for ev_data, _ in best_selection}

        for ev_data, pts_gain in best_selection:
            final_drl[ev_data["drl_category"]] += pts_gain
            if ev_data.get("is_flexible"):
                slot_st, slot_et = allocate_flexible_slot(
                    ev_data["start_time"],
                    ev_data["end_time"],
                    ev_data.get("estimated_hours", 0.5),
                )
            else:
                slot_st, slot_et = ev_data["start_time"], ev_data["end_time"]

            final_events.append(ScheduledDRLEvent(
                task_id=ev_data["id"],
                title=ev_data["title"],
                start_time=slot_st,
                end_time=slot_et,
                location=ev_data["location"],
                training_points=ev_data["training_points"],
                drl_category=ev_data["drl_category"],
                points_gained=pts_gain,
                is_flexible=bool(ev_data.get("is_flexible")),
                window_start=ev_data.get("window_start") or ev_data["start_time"],
                window_end=ev_data.get("window_end") or ev_data["end_time"],
                estimated_hours=float(ev_data.get("estimated_hours", 0.5)),
                is_pinned=False,
                travel_buffer_minutes=ev_data.get("travel_buffer_minutes"),
            ))

        final_events.sort(key=lambda ev: (ev.start_time, ev.end_time))

        unselected_events: List[ScheduledDRLEvent] = []
        for ev_data in feasible_events:
            if id(ev_data) in selected_ids_set:
                continue
            unselected_events.append(ScheduledDRLEvent(
                task_id=ev_data["id"],
                title=ev_data["title"],
                start_time=ev_data["start_time"],
                end_time=ev_data["end_time"],
                location=ev_data["location"],
                training_points=ev_data["training_points"],
                drl_category=ev_data["drl_category"],
                points_gained=ev_data["training_points"],
                is_flexible=bool(ev_data.get("is_flexible")),
                window_start=ev_data.get("window_start") or ev_data["start_time"],
                window_end=ev_data.get("window_end") or ev_data["end_time"],
                estimated_hours=float(ev_data.get("estimated_hours", 0.5)),
                is_pinned=False,
                travel_buffer_minutes=ev_data.get("travel_buffer_minutes"),
            ))

        return BranchAndBoundResult(
            status="OPTIMAL",
            selected_events=final_events,
            total_drl_gained=pinned_drl_gained + best_score,
            initial_drl=base_initial_drl,
            final_drl=final_drl,
            drl_caps=self.drl_caps,
            execution_time_seconds=exec_duration,
            nodes_explored=nodes_count,
            total_candidates_considered=total_candidates,
            global_cap=self.global_cap,
            unselected_events=unselected_events,
            fixed_tasks_summary=fixed_tasks_summary,
            flexible_tasks_summary=list(flexible_workloads),
        )


__all__ = [
    "DEFAULT_DRL_CAPS",
    "MAX_TOTAL_DRL",
    "DRL_CATEGORY_NAMES",
    "DRL_CATEGORY_FULL_NAMES",
    "DRL_CATEGORY_CRITERIA",
    "FIXED_TASK_TYPES",
    "BranchAndBoundResult",
    "BranchAndBoundScheduler",
    "ScheduledDRLEvent",
    "format_location_text",
    "get_travel_buffer_minutes",
    "normalize_drl_category",
    "normalize_location",
    "parse_timestamp",
]
