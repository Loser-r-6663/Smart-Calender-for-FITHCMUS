"""
Kịch bản Kiểm thử Mô phỏng Lịch trình Hoàn chỉnh 1 Tuần (Full 1-Week Schedule Simulation).
Dành cho sinh viên Khoa Công nghệ Thông tin - ĐH Khoa học Tự nhiên, ĐHQG-HCM (FIT - HCMUS).

File này thực hiện:
1. Xây dựng dữ liệu giả lập thực tế trọn vẹn 7 ngày (Thứ Hai 02/11/2026 -> Chủ Nhật 08/11/2026):
   - Tầng 1 (Cố định): 5 ca học lý thuyết/thực hành tại CS1 & CS2 + 1 lịch cá nhân cố định.
   - Tầng 2 (Linh hoạt): 3 bài tập/đồ án Moodle có hạn chót rải đều trong tuần.
   - Tầng 3 (Tùy chọn ĐRL): 9 sự kiện phong trào/học thuật thuộc các Điều 1, 2, 3, 4, 5
     (bao gồm 5 sự kiện hợp lệ, 1 sự kiện online trắc nghiệm chỉ có hạn đóng cổng, và 3 sự kiện bẫy bị loại).
   - Nhịp sinh học tự động: 7 giấc ngủ đêm (23:30 - 06:30) và 14 bữa ăn linh hoạt (7 trưa + 7 tối).
2. Giải bài toán tối ưu hóa bằng Google OR-Tools CP-SAT.
3. In trực quan thời gian biểu chi tiết từng ngày từ Thứ Hai đến Chủ Nhật.
4. Kiểm chứng tự động 6 bất biến toán học (Mathematical Invariants) bằng lệnh assert.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

# Thêm thư mục gốc của dự án vào sys.path để import chuẩn package Backend
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Đảm bảo hiển thị tiếng Việt chuẩn UTF-8 trên mọi terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from Backend.scheduler import (
    ScheduleResult,
    ScheduledItem,
    UserPreferences,
    get_travel_time,
    normalize_location,
    solve_max_drl_schedule,
)
from Backend.task_for_running_scheduling_algo import (
    DRL_CATEGORY_CAPS,
    DRLCategory,
    SourcePlatform,
    Task,
    TaskType,
)


def build_full_week_mock_tasks() -> List[Task]:
    """Khởi tạo danh sách công việc thực tế trong 1 tuần của sinh viên FIT-HCMUS."""
    return [
        # =====================================================================
        # 1. TẦNG 1: THỜI KHÓA BIỂU CỐ ĐỊNH & VIỆC CÁ NHÂN (FIXED ANCHORS)
        # =====================================================================
        Task(
            id="class_calculus_mon",
            title="Vi tích phân 1B (Lý thuyết)",
            type=TaskType.CLASS,
            course_code="MTH10001",
            location="CS1 - Phòng F201",
            start_time=datetime(2026, 11, 2, 7, 30),
            end_time=datetime(2026, 11, 2, 11, 30),
            source_platform=SourcePlatform.PORTAL,
        ),
        Task(
            id="class_intro_prog_tue",
            title="Nhập môn Lập trình (Thực hành Lab)",
            type=TaskType.CLASS,
            course_code="CSC10001",
            location="CS2 - Phòng máy Linh Trung",
            start_time=datetime(2026, 11, 3, 13, 0),
            end_time=datetime(2026, 11, 3, 16, 30),
            source_platform=SourcePlatform.PORTAL,
        ),
        Task(
            id="class_networks_wed",
            title="Mạng máy tính (Lý thuyết)",
            type=TaskType.CLASS,
            course_code="CSC10004",
            location="CS1 - Giảng đường C",
            start_time=datetime(2026, 11, 4, 7, 30),
            end_time=datetime(2026, 11, 4, 11, 30),
            source_platform=SourcePlatform.PORTAL,
        ),
        Task(
            id="class_pe_thu",
            title="Giáo dục thể chất (Bóng chuyền)",
            type=TaskType.CLASS,
            course_code="PE00001",
            location="CS2 - Nhà thi đấu Thủ Đức",
            start_time=datetime(2026, 11, 5, 8, 0),
            end_time=datetime(2026, 11, 5, 10, 30),
            source_platform=SourcePlatform.PORTAL,
        ),
        Task(
            id="class_dsa_fri",
            title="Cấu trúc dữ liệu và Giải thuật",
            type=TaskType.CLASS,
            course_code="CSC10002",
            location="CS1 - Phòng I42",
            start_time=datetime(2026, 11, 6, 13, 30),
            end_time=datetime(2026, 11, 6, 17, 0),
            source_platform=SourcePlatform.PORTAL,
        ),
        Task(
            id="personal_english_sat",
            title="Học IELTS định kỳ tại trung tâm",
            type=TaskType.PERSONAL,
            location="CS1 - Quận 5",
            start_time=datetime(2026, 11, 7, 8, 30),
            end_time=datetime(2026, 11, 7, 11, 0),
            is_manual=True,
            source_platform=SourcePlatform.CUSTOM,
        ),

        # =====================================================================
        # 2. TẦNG 2: BÀI TẬP & ĐỒ ÁN MOODLE LINH HOẠT (FLEXIBLE TASKS)
        # =====================================================================
        Task(
            id="assign_pointers_lab",
            title="Lab 2: Con trỏ & Cấp phát động C++",
            type=TaskType.ASSIGNMENT,
            course_code="CSC10001",
            deadline=datetime(2026, 11, 4, 23, 59),  # Hạn chót: Đêm Thứ Tư
            estimated_hours=3.0,                     # Cần 180 phút
            source_platform=SourcePlatform.MOODLE,
        ),
        Task(
            id="assign_socket_project",
            title="Đồ án Socket Chat Đa luồng",
            type=TaskType.ASSIGNMENT,
            course_code="CSC10004",
            deadline=datetime(2026, 11, 6, 13, 0),   # Hạn chót: Trưa Thứ Sáu (trước giờ học chiều)
            estimated_hours=4.0,                     # Cần 240 phút
            source_platform=SourcePlatform.MOODLE,
        ),
        Task(
            id="assign_dsa_sorting",
            title="Báo cáo Thực nghiệm các thuật toán Sắp xếp",
            type=TaskType.ASSIGNMENT,
            course_code="CSC10002",
            deadline=datetime(2026, 11, 8, 21, 0),   # Hạn chót: Tối Chủ Nhật
            estimated_hours=3.5,                     # Cần 210 phút
            source_platform=SourcePlatform.MOODLE,
        ),

        # =====================================================================
        # 3. TẦNG 3: CÁC SỰ KIỆN ĐRL TÙY CHỌN (OPTIONAL DRL EVENTS)
        # =====================================================================
        # Sự kiện 1 (Hợp lệ - Được chọn): Sáng Thứ Ba tại CS2 (Cùng cơ sở với lớp Lab chiều Thứ Ba)
        Task(
            id="event_ai_seminar",
            title="Tọa đàm Khoa học: Generative AI & Tương lai ngành CNTT",
            type=TaskType.EVENT,
            location="CS2 - Hội trường Linh Trung",
            start_time=datetime(2026, 11, 3, 8, 30),
            end_time=datetime(2026, 11, 3, 11, 30),
            training_points=5,
            drl_category=DRLCategory.DIEU_1,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 2 (Bẫy - Bị loại): Tối Thứ Hai kéo dài tới 24:00 -> Lấn vào giờ ngủ 23:30
        Task(
            id="event_late_gala",
            title="Đêm Gala Chào đón Tân sinh viên (Kéo dài quá khuya)",
            type=TaskType.EVENT,
            location="CS1 - Hội trường C",
            start_time=datetime(2026, 11, 2, 20, 0),
            end_time=datetime(2026, 11, 3, 0, 0),
            training_points=6,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 3 (Bẫy - Bị loại): Sáng Thứ Tư trùng giờ học môn Mạng máy tính
        Task(
            id="event_hackathon_conflict",
            title="Cuộc thi Lập trình HCMUS Hackathon (Trùng lịch học)",
            type=TaskType.EVENT,
            location="CS1 - Tòa F",
            start_time=datetime(2026, 11, 4, 8, 0),
            end_time=datetime(2026, 11, 4, 11, 0),
            training_points=10,
            drl_category=DRLCategory.DIEU_1,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 4 (Hợp lệ - Được chọn): Chiều Thứ Tư tại CS1
        Task(
            id="event_academic_rules",
            title="Buổi phổ biến Quy chế Học vụ & Chính sách Học bổng",
            type=TaskType.EVENT,
            location="CS1 - Hội trường I",
            start_time=datetime(2026, 11, 4, 14, 0),
            end_time=datetime(2026, 11, 4, 16, 30),
            training_points=5,
            drl_category=DRLCategory.DIEU_2,
            source_platform=SourcePlatform.PORTAL,
        ),
        # Sự kiện 5 (Bẫy - Bị loại): Trưa Thứ Năm lúc 11:00 tại CS1, nhưng vừa học Thể dục ở CS2 đến 10:30 (Thiếu 65p chạy xe)
        Task(
            id="event_sports_fest_travel_trap",
            title="Ngày hội Thể thao Đoàn Khoa FIT (Không kịp chạy xe CS2->CS1)",
            type=TaskType.EVENT,
            location="CS1 - Sân trường Q5",
            start_time=datetime(2026, 11, 5, 11, 0),
            end_time=datetime(2026, 11, 5, 13, 30),
            training_points=8,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 6 (Hợp lệ - Được chọn): Sáng Thứ Sáu tại CS1 (Cùng cơ sở với lớp CTDL buổi chiều)
        Task(
            id="event_blood_donation",
            title="Ngày hội Hiến máu Tình nguyện Giọt hồng Yêu thương",
            type=TaskType.EVENT,
            location="CS1 - Sảnh tòa nhà C",
            start_time=datetime(2026, 11, 6, 8, 0),
            end_time=datetime(2026, 11, 6, 11, 0),
            training_points=8,
            drl_category=DRLCategory.DIEU_4,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 7 (Hợp lệ - Được chọn): Chiều Thứ Bảy Online qua MS Teams (Không tốn thời gian di chuyển)
        Task(
            id="event_online_cv_workshop",
            title="Webinar Kỹ năng viết CV & Phỏng vấn Thực tập sinh IT",
            type=TaskType.EVENT,
            location="Online - MS Teams",
            start_time=datetime(2026, 11, 7, 14, 0),
            end_time=datetime(2026, 11, 7, 16, 30),
            training_points=4,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 8 (Hợp lệ - Được chọn): Sáng Chủ Nhật chiến dịch tình nguyện
        Task(
            id="event_green_sunday",
            title="Chiến dịch Chủ Nhật Xanh - Bảo vệ Môi trường Đô thị",
            type=TaskType.EVENT,
            location="CS2 - Khu đô thị ĐHQG-HCM",
            start_time=datetime(2026, 11, 8, 8, 0),
            end_time=datetime(2026, 11, 8, 11, 0),
            training_points=6,
            drl_category=DRLCategory.DIEU_4,
            source_platform=SourcePlatform.FACEBOOK,
        ),
        # Sự kiện 9 (Hợp lệ - Online chỉ có end_time, không có start_time):
        # Cuộc thi trắc nghiệm trực tuyến đóng cổng lúc 22:00 tối Thứ Năm
        Task(
            id="event_online_law_quiz",
            title="Thi trắc nghiệm trực tuyến Tìm hiểu Pháp luật & Nội quy (Chỉ có hạn đóng)",
            type=TaskType.EVENT,
            location="Online - MyAloha",
            start_time=None,
            end_time=datetime(2026, 11, 5, 22, 0),
            training_points=3,
            drl_category=DRLCategory.DIEU_2,
            source_platform=SourcePlatform.PORTAL,
        ),
    ]


def verify_weekly_schedule_invariants(
    result: ScheduleResult,
    tasks: List[Task],
    current_drl_points: Dict[str, int],
    prefs: UserPreferences,
) -> None:
    """
    Kiểm chứng tự động 6 bất biến toán học (Mathematical Invariants) của lịch tuần:
    1. Trạng thái giải phải đạt OPTIMAL hoặc FEASIBLE.
    2. Không có bất kỳ 2 hoạt động nào chồng lấn thời gian (Strict No-Overlap).
    3. Thời gian chuyển tiếp giữa CS1 và CS2 phải >= 65 phút (50p chạy xe + 15p nghỉ).
    4. Toàn bộ 3 bài tập Moodle đều được xếp lịch và hoàn thành trước hạn chót.
    5. Bảo toàn đủ 7 giấc ngủ đêm (420p/đêm) và 14 bữa ăn (7 trưa + 7 tối).
    6. Điểm ĐRL cộng thêm tuân thủ đúng trần quy chế 5 Điều (Submodular Capping).
    """
    # 1. Kiểm tra trạng thái nghiệm
    assert result.status in ("OPTIMAL", "FEASIBLE"), f"Bộ giải thất bại với trạng thái: {result.status}"

    items = result.scheduled_items

    # 2. Kiểm tra bất biến không trùng lặp (No-Overlap)
    for idx in range(len(items) - 1):
        curr_item = items[idx]
        next_item = items[idx + 1]
        assert curr_item.end_time <= next_item.start_time, (
            f"Vi phạm No-Overlap giữa '{curr_item.title}' ({curr_item.start_time} -> {curr_item.end_time}) "
            f"và '{next_item.title}' ({next_item.start_time} -> {next_item.end_time})"
        )

    # 3. Kiểm tra bất biến di chuyển địa lý giữa các sự kiện/lớp học cố định
    campus_items = [
        it for it in items if it.item_type in ("class", "event", "personal") and it.location
    ]
    for idx in range(len(campus_items) - 1):
        item_a = campus_items[idx]
        item_b = campus_items[idx + 1]
        req_travel = get_travel_time(item_a.location, item_b.location, prefs)
        if req_travel > 0:
            actual_gap_min = (item_b.start_time - item_a.end_time).total_seconds() / 60.0
            assert actual_gap_min >= req_travel, (
                f"Vi phạm thời gian di chuyển CS1<->CS2 giữa '{item_a.title}' và '{item_b.title}': "
                f"Cần {req_travel}p nhưng chỉ có {actual_gap_min:.0f}p"
            )

    # 4. Kiểm tra toàn bộ bài tập linh hoạt hoàn thành trước deadline
    expected_assignments = [t for t in tasks if t.is_flexible_task]
    assert len(result.scheduled_assignment_slots) == len(expected_assignments), (
        "Số lượng bài tập được xếp lịch không khớp với đầu vào!"
    )
    for assign_slot in result.scheduled_assignment_slots:
        orig_task = next(t for t in expected_assignments if t.id == assign_slot.task_id)
        assert orig_task.deadline is not None
        assert assign_slot.end_time <= orig_task.deadline, (
            f"Bài tập '{orig_task.title}' kết thúc lúc {assign_slot.end_time}, trễ hơn hạn chót {orig_task.deadline}!"
        )
        assert assign_slot.duration_minutes == orig_task.duration_minutes, (
            f"Thời lượng làm bài '{orig_task.title}' không khớp!"
        )

    # 5. Kiểm tra bảo toàn nhịp sinh học (7 giấc ngủ đêm + 14 bữa ăn)
    sleep_items = [it for it in items if it.item_type == "sleep"]
    meal_items = [it for it in items if it.item_type == "meal"]
    assert len(sleep_items) == 7, f"Phải có đúng 7 giấc ngủ đêm, nhưng thực tế có {len(sleep_items)}!"
    assert len(meal_items) == 14, f"Phải có đúng 14 bữa ăn (7 trưa + 7 tối), nhưng thực tế có {len(meal_items)}!"

    # 6. Kiểm tra các sự kiện bẫy bắt buộc phải bị loại và các sự kiện tốt (gồm cả online chỉ có end_time) được chọn
    assert "event_late_gala" not in result.selected_event_ids, "Sự kiện lấn giờ ngủ 23:30 phải bị loại!"
    assert "event_hackathon_conflict" not in result.selected_event_ids, "Sự kiện trùng giờ học phải bị loại!"
    assert "event_sports_fest_travel_trap" not in result.selected_event_ids, "Sự kiện thiếu thời gian chạy xe phải bị loại!"
    assert "event_online_law_quiz" in result.selected_event_ids, "Sự kiện ĐRL online chỉ có end_time phải được chọn!"

    for cat, gained in result.drl_gained_by_category.items():
        cap = DRL_CATEGORY_CAPS[cat]
        curr = current_drl_points.get(cat, 0)
        assert curr + gained <= cap, f"Điểm tiêu chí {cat} vượt trần quy chế ({curr} + {gained} > {cap})!"


def print_full_week_schedule_report(
    result: ScheduleResult,
    tasks: List[Task],
    week_start: date,
    current_drl_points: Dict[str, int],
) -> None:
    """In báo cáo lịch trình 7 ngày trực quan ra màn hình console."""
    day_names_vn = [
        "THỨ HAI",
        "THỨ BA",
        "THỨ TƯ",
        "THỨ NĂM",
        "THỨ SÁU",
        "THỨ BẢY",
        "CHỦ NHẬT",
    ]
    type_labels = {
        "class": "HỌC PHẦN  ",
        "personal": "CÁ NHÂN   ",
        "assignment": "BÀI TẬP   ",
        "event": "SỰ KIỆN ĐRL",
        "meal": "BỮA ĂN    ",
        "sleep": "GIẤC NGỦ  ",
    }

    print("=" * 100)
    print("BÁO CÁO KẾT QUẢ MÔ PHỎNG LẬP LỊCH TỐI ƯU TOÀN DIỆN 1 TUẦN (GOOGLE OR-TOOLS CP-SAT)")
    print(
        f"Tuần: {week_start.strftime('%d/%m/%Y')} -> {(week_start + timedelta(days=6)).strftime('%d/%m/%Y')} | "
        f"Trạng thái: {result.status} | Thời gian giải: {result.solve_time_seconds:.4f}s"
    )
    print("=" * 100)

    # 1. Bảng tổng hợp Điểm Rèn Luyện theo 5 Điều
    print("\n[I] BẢNG ĐỐI SOÁT ĐIỂM RÈN LUYỆN THEO 5 ĐIỀU QUY CHẾ ĐHKHTN:")
    print("-" * 88)
    print(f"{'Tiêu chí':<12} | {'Điểm hiện có':<15} | {'Điểm cộng thêm':<16} | {'Tổng sau tuần':<15} | {'Trần tối đa':<12}")
    print("-" * 88)
    for cat_key, cap_val in DRL_CATEGORY_CAPS.items():
        curr_val = current_drl_points.get(cat_key, 0)
        gained_val = result.drl_gained_by_category.get(cat_key, 0)
        after_val = curr_val + gained_val
        print(
            f"{cat_key:<12} | {curr_val:>12} đ  | {'+' + str(gained_val):>13} đ  | "
            f"{after_val:>12} đ  | {cap_val:>9} đ"
        )
    print("-" * 88)
    print(f">>> TỔNG ĐIỂM RÈN LUYỆN THỰC TẾ TĂNG THÊM TRONG TUẦN: +{result.total_drl_gained} ĐIỂM <<<")

    # 2. Phân tích quyết định chọn / loại sự kiện ĐRL của Solver
    print("\n[II] PHÂN TÍCH QUYẾT ĐỊNH LỰA CHỌN SỰ KIỆN ĐRL CỦA BỘ GIẢI:")
    all_events = [t for t in tasks if t.is_optional_drl_event]
    for ev in all_events:
        is_selected = ev.id in result.selected_event_ids
        status_tag = "[ĐƯỢC CHỌN]" if is_selected else "[BỊ LOẠI]  "
        if ev.start_time and ev.end_time:
            time_info = f"{ev.start_time.strftime('%a %d/%m %H:%M')}-{ev.end_time.strftime('%H:%M')}"
        else:
            eff_end = ev.end_time or ev.deadline
            time_info = f"Hạn: {eff_end.strftime('%a %d/%m %H:%M'):<16}" if eff_end else "Linh hoạt"
        cat_str = ev.drl_category.value if ev.drl_category else ""
        print(f"  {status_tag} {time_info:<21} | +{ev.training_points:2d}đ ({cat_str}) | {ev.title} [{ev.location}]")

    # 3. Chi tiết thời gian biểu từng ngày (Thứ Hai -> Chủ Nhật)
    print("\n[III] THỜI GIAN BIỂU CHI TIẾT 7 NGÀY TRONG TUẦN:")
    for day_idx in range(7):
        curr_date = week_start + timedelta(days=day_idx)
        day_start = datetime(curr_date.year, curr_date.month, curr_date.day, 0, 0, 0)
        day_end = day_start + timedelta(days=1)

        # Lấy các hoạt động bắt đầu trong ngày curr_date
        day_items = [
            it for it in result.scheduled_items if day_start <= it.start_time < day_end
        ]

        print("\n" + "-" * 100)
        print(f" NGÀY {day_idx + 1}: {day_names_vn[day_idx]} ({curr_date.strftime('%d/%m/%Y')}) — Tổng {len(day_items)} hoạt động")
        print("-" * 100)
        for item in day_items:
            t_start = item.start_time.strftime("%H:%M")
            # Nếu kết thúc qua ngày hôm sau (ví dụ giấc ngủ đêm), hiển thị kèm (+1d)
            if item.end_time.date() > item.start_time.date():
                t_end = f"{item.end_time.strftime('%H:%M')} (+1d)"
            else:
                t_end = item.end_time.strftime("%H:%M")

            label = type_labels.get(item.item_type, item.item_type.upper().ljust(10))
            loc_str = f"@ {item.location}" if item.location else ""
            dur_str = f"({item.duration_minutes}p)"
            print(f"  {t_start:>5} -> {t_end:<11} {dur_str:<7} | [{label}] | {item.title} {loc_str}")

    # 4. Thông số kỹ thuật từ bộ giải CP-SAT
    print("\n" + "=" * 100)
    print("[IV] THỐNG KÊ KỸ THUẬT TỪ BỘ GIẢI GOOGLE OR-TOOLS CP-SAT (SOLVER RESPONSE STATS):")
    print("-" * 100)
    print(result.solver_stats.strip())
    print("=" * 100)


def run_full_week_simulation() -> ScheduleResult:
    """Chạy toàn bộ kịch bản mô phỏng lịch 1 tuần, in báo cáo và kiểm tra bất biến."""
    week_start = date(2026, 11, 2)             # Thứ Hai 02/11/2026
    now_dt = datetime(2026, 11, 2, 6, 45, 0)   # Thời điểm lập lịch: 06:45 sáng Thứ Hai

    # Điểm rèn luyện tích lũy hiện tại của sinh viên trước tuần này
    student_current_drl: Dict[str, int] = {
        DRLCategory.DIEU_1.value: 27,  # Trần 30 -> Chỉ còn thiếu 3 điểm (Sự kiện AI 5đ chỉ nhận +3đ)
        DRLCategory.DIEU_2.value: 12,  # Trần 20 -> Còn thiếu 8 điểm
        DRLCategory.DIEU_3.value: 15,  # Trần 25 -> Còn thiếu 10 điểm
        DRLCategory.DIEU_4.value: 10,  # Trần 25 -> Còn thiếu 15 điểm
        DRLCategory.DIEU_5.value: 0,   # Trần 30 -> Còn thiếu 30 điểm
    }

    prefs = UserPreferences()
    tasks = build_full_week_mock_tasks()

    result = solve_max_drl_schedule(
        tasks=tasks,
        week_start=week_start,
        now=now_dt,
        current_drl_points=student_current_drl,
        preferences=prefs,
        timeout_seconds=3.0,
    )

    print_full_week_schedule_report(result, tasks, week_start, student_current_drl)
    verify_weekly_schedule_invariants(result, tasks, student_current_drl, prefs)

    print("\n>>> KIỂM CHỨNG TOÀN DIỆN 6 BẤT BIẾN TOÁN HỌC TRÊN LỊCH TUẦN: 100% PASSED! <<<\n")
    return result


if __name__ == "__main__":
    run_full_week_simulation()

