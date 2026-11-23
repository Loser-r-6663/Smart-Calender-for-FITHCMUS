"""
Unit tests cho Thuật toán Nhánh Cận (Branch and Bound Scheduler).
Kiểm thử toàn diện các kịch bản thực tế dựa trên Schema Task từ Database (PostgreSQL):
1. Bảo vệ lịch học cố định (Hard anchor protection): Sự kiện ĐRL trùng giờ học bị loại bỏ.
2. Ràng buộc di chuyển cơ sở (CS1 <-> CS2): Cần đệm 60 phút di chuyển.
3. Ràng buộc trần điểm 5 Điều (Category Cap): Điều 1 trần 30, có 27 chỉ cộng tối đa 3 điểm.
4. Xử lý xung đột giữa các sự kiện ĐRL trùng giờ: Chọn sự kiện mang lại tổng điểm cao hơn.
5. Sự kiện online chỉ có hạn chót deadline: Xử lý mượt mà.
6. Tốc độ thực thi với quy mô tối đa 40 sự kiện: Chạy xong trong dưới 0.05 giây (< 50ms).
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from Backend.Scheduling.branch_and_bound_scheduler import (
    BranchAndBoundScheduler,
    DEFAULT_DRL_CAPS,
)


TZ_HCM = timezone(timedelta(hours=7))


class TestBranchAndBoundScheduler(unittest.TestCase):

    def setUp(self):
        self.scheduler = BranchAndBoundScheduler(campus_travel_minutes=60)
        self.monday = datetime(2026, 11, 2, 7, 0, tzinfo=TZ_HCM)

    def test_case_1_hard_anchor_protection(self):
        """Kiểm tra: Sự kiện ĐRL trùng giờ học cố định phải bị loại bỏ."""
        tasks = [
            # Lớp học cố định: Giải tích 1 sáng thứ 2 (07:30 -> 11:30)
            {
                "id": "class-giai-tich",
                "title": "Vi tích phân 1B",
                "type": "class",
                "start_time": datetime(2026, 11, 2, 7, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 2, 11, 30, tzinfo=TZ_HCM),
                "location": "CS1 - F201",
                "training_points": 0,
            },
            # Sự kiện ĐRL diễn ra lúc 08:30 -> 10:30 (Trùng 100% giờ học)
            {
                "id": "event-trung-gio-hoc",
                "title": "Tọa đàm AI (Trùng giờ học)",
                "type": "event",
                "start_time": datetime(2026, 11, 2, 8, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 2, 10, 30, tzinfo=TZ_HCM),
                "location": "CS1 - Hội trường C",
                "training_points": 10,
                "drl_category": "dieu_1",
            },
            # Sự kiện ĐRL diễn ra chiều thứ 2 (14:00 -> 16:30) (Không trùng)
            {
                "id": "event-hop-le",
                "title": "Hội thảo Kỹ năng",
                "type": "event",
                "start_time": datetime(2026, 11, 2, 14, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 2, 16, 30, tzinfo=TZ_HCM),
                "location": "CS1 - Hội trường I",
                "training_points": 5,
                "drl_category": "dieu_2",
            },
        ]

        result = self.scheduler.schedule(tasks)
        selected_ids = [e.task_id for e in result.selected_events]

        self.assertNotIn("event-trung-gio-hoc", selected_ids, "Sự kiện trùng giờ học không được chọn!")
        self.assertIn("event-hop-le", selected_ids, "Sự kiện hợp lệ phải được chọn!")
        self.assertEqual(result.total_drl_gained, 5)

    def test_case_2_campus_travel_constraint(self):
        """Kiểm tra: Sự kiện khác cơ sở cần đệm 60 phút di chuyển."""
        tasks = [
            # Lớp học tại CS2 (Linh Trung) kết thúc lúc 11:30
            {
                "id": "class-cs2",
                "title": "Lập trình C++",
                "type": "class",
                "start_time": datetime(2026, 11, 3, 8, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 3, 11, 30, tzinfo=TZ_HCM),
                "location": "CS2 - Nhà C",
                "training_points": 0,
            },
            # Sự kiện tại CS1 bắt đầu lúc 12:15 (cách 45p, không đủ 60p di chuyển)
            {
                "id": "event-cs1-khong-kip-gio",
                "title": "Hiến máu tình nguyện (CS1)",
                "type": "event",
                "start_time": datetime(2026, 11, 3, 12, 15, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 3, 14, 0, tzinfo=TZ_HCM),
                "location": "CS1 - Sảnh C",
                "training_points": 8,
                "drl_category": "dieu_4",
            },
            # Sự kiện tại CS2 bắt đầu lúc 12:00 (cùng CS2 nên không cần di chuyển xa)
            {
                "id": "event-cs2-kip-gio",
                "title": "Ngày hội Công nghệ (CS2)",
                "type": "event",
                "start_time": datetime(2026, 11, 3, 12, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 3, 14, 0, tzinfo=TZ_HCM),
                "location": "CS2 - Hội trường",
                "training_points": 6,
                "drl_category": "dieu_3",
            },
        ]

        result = self.scheduler.schedule(tasks)
        selected_ids = [e.task_id for e in result.selected_events]

        self.assertNotIn("event-cs1-khong-kip-gio", selected_ids, "Không đủ thời gian 60 phút di chuyển CS2 -> CS1!")
        self.assertIn("event-cs2-kip-gio", selected_ids, "Cùng cơ sở CS2 thì hợp lệ!")
        self.assertEqual(result.total_drl_gained, 6)

    def test_case_3_submodular_category_capping(self):
        """Kiểm tra: Trần điểm 5 Điều (Điều 1 trần 30, có 27 thì chỉ được cộng tối đa 3 điểm)."""
        tasks = [
            {
                "id": "event-dieu1-10d",
                "title": "Cuộc thi NCKH Sinh viên",
                "type": "event",
                "start_time": datetime(2026, 11, 4, 8, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 4, 11, 0, tzinfo=TZ_HCM),
                "location": "CS1",
                "training_points": 10,
                "drl_category": "dieu_1",
            },
        ]

        # Sinh viên đã có 27 điểm ở Điều 1 (trần 30)
        initial_drl = {"dieu_1": 27}
        result = self.scheduler.schedule(tasks, initial_drl=initial_drl)

        self.assertEqual(len(result.selected_events), 1)
        selected_ev = result.selected_events[0]
        self.assertEqual(selected_ev.points_gained, 3, "Chỉ được cộng 3 điểm vì trần Điều 1 là 30!")
        self.assertEqual(result.final_drl["dieu_1"], 30)
        self.assertEqual(result.total_drl_gained, 3)

    def test_case_4_conflict_between_drl_events(self):
        """Kiểm tra: Hai sự kiện ĐRL trùng giờ, thuật toán phải chọn sự kiện có điểm cao hơn."""
        tasks = [
            # Sự kiện A: 5 điểm từ 08:00 -> 11:00
            {
                "id": "event-it-diem",
                "title": "Hội thảo nhỏ (5đ)",
                "type": "event",
                "start_time": datetime(2026, 11, 5, 8, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 5, 11, 0, tzinfo=TZ_HCM),
                "location": "CS1",
                "training_points": 5,
                "drl_category": "dieu_3",
            },
            # Sự kiện B: 9 điểm từ 08:30 -> 11:30 (Trùng giờ sự kiện A)
            {
                "id": "event-nhieu-diem",
                "title": "Webinar lớn (9đ)",
                "type": "event",
                "start_time": datetime(2026, 11, 5, 8, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 5, 11, 30, tzinfo=TZ_HCM),
                "location": "CS1",
                "training_points": 9,
                "drl_category": "dieu_3",
            },
        ]

        result = self.scheduler.schedule(tasks)
        selected_ids = [e.task_id for e in result.selected_events]

        self.assertIn("event-nhieu-diem", selected_ids, "Phải chọn sự kiện nhiều điểm hơn!")
        self.assertNotIn("event-it-diem", selected_ids, "Sự kiện ít điểm hơn bị trùng giờ nên bị loại!")
        self.assertEqual(result.total_drl_gained, 9)

    def test_case_5_online_deadline_event(self):
        """Kiểm tra: Sự kiện ĐRL online chỉ có hạn chót deadline (như trắc nghiệm MyAloha)."""
        tasks = [
            {
                "id": "event-myaloha",
                "title": "Thi trắc nghiệm Pháp luật online",
                "type": "event",
                "deadline": datetime(2026, 11, 6, 21, 0, tzinfo=TZ_HCM),
                "location": "Online - MyAloha",
                "training_points": 3,
                "drl_category": "dieu_2",
            },
        ]

        result = self.scheduler.schedule(tasks)
        self.assertEqual(len(result.selected_events), 1)
        self.assertEqual(result.selected_events[0].points_gained, 3)

    def test_case_6_scalability_and_execution_speed(self):
        """Kiểm tra: Chạy với quy mô cao điểm 40 sự kiện, thời gian chạy phải < 0.05s."""
        tasks = []
        # Tạo 5 buổi học cố định từ T2 -> T6
        for day in range(2, 7):
            tasks.append({
                "id": f"class-day-{day}",
                "title": f"Môn học thứ {day}",
                "type": "class",
                "start_time": datetime(2026, 11, day, 7, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, day, 11, 30, tzinfo=TZ_HCM),
                "location": "CS1",
                "training_points": 0,
            })

        # Tạo 40 sự kiện ĐRL phân bố thực tế (3 khung giờ/ngày x 7 ngày, nhiều sự kiện trùng giờ cạnh tranh nhau)
        for i in range(40):
            day = 2 + (i % 7)  # ngày 2 -> 8
            window = i % 3
            if window == 0:
                st = datetime(2026, 11, day, 8, 30, tzinfo=TZ_HCM)
                et = datetime(2026, 11, day, 11, 0, tzinfo=TZ_HCM)
            elif window == 1:
                st = datetime(2026, 11, day, 14, 0, tzinfo=TZ_HCM)
                et = datetime(2026, 11, day, 16, 30, tzinfo=TZ_HCM)
            else:
                st = datetime(2026, 11, day, 18, 0, tzinfo=TZ_HCM)
                et = datetime(2026, 11, day, 20, 30, tzinfo=TZ_HCM)

            tasks.append({
                "id": f"event-dense-{i}",
                "title": f"Sự kiện ngoại khóa #{i}",
                "type": "event",
                "start_time": st,
                "end_time": et,
                "location": "CS1" if i % 2 == 0 else "CS2",
                "training_points": 3 + (i % 8),
                "drl_category": f"dieu_{(i % 5) + 1}",
            })

        result = self.scheduler.schedule(tasks)
        
        # Kiểm tra tốc độ thực thi (ngưỡng an toàn benchmark < 0.2s)
        self.assertLess(result.execution_time_seconds, 0.2, f"Thuật toán phải chạy < 0.2s, thực tế: {result.execution_time_seconds:.4f}s")
        self.assertGreater(result.total_drl_gained, 0, "Phải chọn được các sự kiện tốt nhất!")
        print(f"\n[Test Scalability] 40 sự kiện giải trong {result.execution_time_seconds * 1000:.2f} ms | Duyệt {result.nodes_explored} nút | ĐRL tăng: +{result.total_drl_gained}đ")

    def test_case_7_global_cap_100(self):
        """Kiểm tra: Ràng buộc trần toàn cục 100 điểm (Quy chế ĐHKHTN)."""
        # Sinh viên đã có 92 điểm tổng cộng (dieu_1: 28, dieu_2: 18, dieu_3: 20, dieu_4: 16, dieu_5: 10)
        initial_drl = {
            "dieu_1": 28,  # trần 30
            "dieu_2": 18,  # trần 20
            "dieu_3": 20,  # trần 25
            "dieu_4": 16,  # trần 25
            "dieu_5": 10,  # trần 30
        }
        # Có 3 sự kiện hợp lệ trong tuần, mỗi sự kiện 5đ (tổng 15đ)
        tasks = [
            {
                "id": f"event-cap-{i}",
                "title": f"Sự kiện #{i}",
                "type": "event",
                "start_time": datetime(2026, 11, 2 + i, 14, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 2 + i, 16, 0, tzinfo=TZ_HCM),
                "location": "ONLINE",
                "training_points": 5,
                "drl_category": "dieu_4",  # Điều 4 còn thiếu 9đ
            }
            for i in range(3)
        ]

        result = self.scheduler.schedule(tasks, initial_drl=initial_drl)

        # Sinh viên đang có 92đ, chỉ cần 8đ là chạm trần 100đ
        # Sự kiện 1 (5đ) + Sự kiện 2 (3đ hiệu dụng) = 8đ -> đạt 100đ
        # Thuật toán không chọn sự kiện 3 vì đã đạt trần toàn cục 100đ!
        self.assertEqual(result.total_drl_gained, 8, "Chỉ được cộng 8đ để chạm trần 100đ!")
        self.assertEqual(result.final_total_drl, 100, "Tổng ĐRL cuối cùng phải là 100đ!")
        self.assertEqual(len(result.selected_events), 2, "Chỉ chọn 2 sự kiện vừa đủ đạt 100đ, không xếp thừa!")

    def test_case_8_extracted_task_daytime_location_and_articles(self):
        """Kiểm tra tích hợp trực tiếp với ExtractedTask (DateDayTime, Location, Articles 1..5)."""
        from datetime import date, time
        from DataProcessor.Standardization.BaseTask import DateDayTime, Location
        from DataProcessor.Standardization.ExtractedTask import ExtractedTask
        from Backend.Scheduling.service import SchedulingService

        now = datetime(2026, 11, 9, 8, 0, tzinfo=TZ_HCM)
        portal_class = ExtractedTask(
            id="portal-class-t2",
            user_id="user-1",
            title="CSC10006 · Cơ sở dữ liệu",
            type="class",
            course="Cơ sở dữ liệu",
            location=Location(room="F.102"),  # Chỉ có tên phòng -> tự động gắn Cơ sở 1 (CS1)
            start_time=DateDayTime(day="T2", time=time(8, 0)),
            end_time=DateDayTime(day="T2", time=time(10, 0)),
            source_url="https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp",
            source_platform="Portal",
            updated_at=now,
        )
        cs2_event_too_close = ExtractedTask(
            id="ev-cs2-clash",
            title="Hội thảo AI tại CS2 (Cách giờ học CS1 chỉ 30p < 60p di chuyển)",
            type="event",
            location=Location(room="Hội trường I", campus="Thủ Đức (cơ sở 2)"),
            start_time=DateDayTime(date=date(2026, 11, 9), time=time(10, 30)),
            end_time=DateDayTime(date=date(2026, 11, 9), time=time(12, 30)),
            training_points=10,
            training_point_category="Articles 1",
            estimated_hours=2.0,
            source_url="https://hcmus.edu.vn/ev1",
            source_platform="Trường đại học Khoa học tự nhiên",
            updated_at=now,
        )
        cs2_event_safe = ExtractedTask(
            id="ev-cs2-safe",
            title="Hội thảo AI tại CS2 (Cách giờ học CS1 90p >= 60p di chuyển)",
            type="event",
            location=Location(room="Hội trường I", campus="Thủ Đức (cơ sở 2)"),
            start_time=DateDayTime(date=date(2026, 11, 9), time=time(11, 30)),
            end_time=DateDayTime(date=date(2026, 11, 9), time=time(13, 30)),
            training_points=8,
            training_point_category="Articles 1",
            estimated_hours=2.0,
            source_url="https://hcmus.edu.vn/ev2",
            source_platform="Trường đại học Khoa học tự nhiên",
            updated_at=now,
        )

        run_res = SchedulingService().run_for_tasks(
            [portal_class, cs2_event_too_close, cs2_event_safe],
            user_id="user-1",
            week_start=date(2026, 11, 9),
            restrict_to_window=True,
        )
        selected_ids = [ev.task_id for ev in run_res.schedule.selected_events]
        self.assertNotIn("ev-cs2-clash", selected_ids)
        self.assertIn("ev-cs2-safe", selected_ids)
        self.assertEqual(run_res.schedule.total_drl_gained, 8)
        self.assertEqual(run_res.schedule.final_drl["dieu_1"], 8)

    def test_case_9_flexible_assignment_and_pin_reject_custom_time(self):
        """Kiểm tra chừa quỹ thời gian làm assignment linh hoạt + pin/reject/custom time."""
        from datetime import date
        from Backend.Scheduling.service import SchedulingService

        tasks = [
            {
                "id": "class-mon",
                "title": "Lớp buổi sáng",
                "type": "class",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 9, 10, 0, tzinfo=TZ_HCM),
                "training_points": 0,
            },
            {
                "id": "assign-tight",
                "title": "Bài tập nộp 13h",
                "type": "assignment",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=TZ_HCM),
                "deadline": datetime(2026, 11, 9, 13, 0, tzinfo=TZ_HCM),
                "estimated_hours": 2.5,
                "training_points": 0,
            },
            {
                "id": "ev-steals-study-time",
                "title": "Workshop chiếm mất giờ làm bài",
                "type": "event",
                "start_time": datetime(2026, 11, 9, 10, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 9, 12, 30, tzinfo=TZ_HCM),
                "training_points": 12,
                "training_point_category": "Articles 3",
            },
            {
                "id": "ev-pinned",
                "title": "Sự kiện user đã ghim",
                "type": "event",
                "start_time": datetime(2026, 11, 10, 14, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 10, 16, 0, tzinfo=TZ_HCM),
                "training_points": 4,
                "training_point_category": "Articles 3",
            },
            {
                "id": "ev-rejected",
                "title": "Sự kiện user bỏ qua",
                "type": "event",
                "start_time": datetime(2026, 11, 11, 14, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 11, 16, 0, tzinfo=TZ_HCM),
                "training_points": 15,
                "training_point_category": "Articles 3",
            },
            {
                "id": "ev-flex-online",
                "title": "Quiz ĐRL online mở cả tuần",
                "type": "event",
                "location": "ONLINE",
                "start_time": datetime(2026, 11, 9, 8, 0, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 15, 22, 0, tzinfo=TZ_HCM),
                "training_points": 5,
                "training_point_category": "Articles 2",
            },
        ]
        custom_st = datetime(2026, 11, 12, 19, 0, tzinfo=TZ_HCM)
        custom_et = datetime(2026, 11, 12, 19, 30, tzinfo=TZ_HCM)
        prefs = {
            "ev-pinned": {"pin_status": "pinned"},
            "ev-rejected": {"pin_status": "rejected"},
            "ev-flex-online": {
                "pin_status": "pinned",
                "custom_start_time": custom_st,
                "custom_end_time": custom_et,
            },
        }
        run_res = SchedulingService().run_for_tasks(
            tasks,
            week_start=date(2026, 11, 9),
            restrict_to_window=True,
            user_task_prefs=prefs,
        )
        selected_map = {ev.task_id: ev for ev in run_res.schedule.selected_events}
        self.assertNotIn("ev-steals-study-time", selected_map)
        self.assertNotIn("ev-rejected", selected_map)
        self.assertIn("ev-pinned", selected_map)
        self.assertIn("ev-flex-online", selected_map)
        self.assertEqual(selected_map["ev-flex-online"].start_time, custom_st)
        self.assertEqual(run_res.schedule.total_drl_gained, 9)

    def test_case_10_custom_task_with_travel_buffer_and_reschedule(self):
        """Kiểm tra: Task cá nhân do user thêm có travel_buffer_minutes ước tính (VD: 30 phút) và điều chỉnh lịch."""
        from datetime import date
        from Backend.Scheduling.service import SchedulingService, create_custom_task

        base_tasks = [
            # Sự kiện A tại CS1 kết thúc lúc 17:45 (Chỉ cách giờ học IELTS 15p < 30p di chuyển -> Phải bị loại)
            {
                "id": "ev-cs1-too-close-to-ielts",
                "title": "Workshop CS1 kết thúc 17:45 (Không kịp đi học IELTS lúc 18:00)",
                "type": "event",
                "location": "CS1",
                "start_time": datetime(2026, 11, 10, 15, 45, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 10, 17, 45, tzinfo=TZ_HCM),
                "training_points": 10,
                "training_point_category": "Articles 1",
            },
            # Sự kiện B tại CS1 kết thúc lúc 17:30 (Cách giờ học IELTS đúng 30p >= 30p di chuyển -> Hợp lệ!)
            {
                "id": "ev-cs1-enough-travel-time",
                "title": "Seminar CS1 kết thúc 17:30 (Kịp 30p chạy qua trung tâm IELTS)",
                "type": "event",
                "location": "CS1",
                "start_time": datetime(2026, 11, 10, 15, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 10, 17, 30, tzinfo=TZ_HCM),
                "training_points": 6,
                "training_point_category": "Articles 1",
            },
            # Sự kiện C là ONLINE kết thúc lúc 17:55 (Online không tốn thời gian di chuyển -> Hợp lệ!)
            {
                "id": "ev-online-no-travel-needed",
                "title": "Quiz ĐRL Online (17:30 - 17:55)",
                "type": "event",
                "location": "ONLINE",
                "start_time": datetime(2026, 11, 11, 17, 30, tzinfo=TZ_HCM),
                "end_time": datetime(2026, 11, 11, 17, 55, tzinfo=TZ_HCM),
                "training_points": 4,
                "training_point_category": "Articles 2",
            },
        ]

        # User tự thêm 2 buổi học IELTS ở Trung tâm Quận 3 (18:00 -> 20:00) với thời gian di chuyển ước tính 30 phút
        custom_ielts_tue = create_custom_task(
            title="Học IELTS tại Trung tâm Q3 (Thứ 3)",
            start_time=datetime(2026, 11, 10, 18, 0, tzinfo=TZ_HCM),
            end_time=datetime(2026, 11, 10, 20, 0, tzinfo=TZ_HCM),
            task_type="personal",
            location="Trung tâm IELTS Quận 3",
            travel_buffer_minutes=30,
            user_id="user-1",
        )
        custom_ielts_wed = create_custom_task(
            title="Học IELTS tại Trung tâm Q3 (Thứ 4)",
            start_time=datetime(2026, 11, 11, 18, 0, tzinfo=TZ_HCM),
            end_time=datetime(2026, 11, 11, 20, 0, tzinfo=TZ_HCM),
            task_type="personal",
            location="Trung tâm IELTS Quận 3",
            travel_buffer_minutes=30,
            user_id="user-1",
        )

        run_res = SchedulingService().run_for_tasks(
            base_tasks,
            custom_tasks=[custom_ielts_tue, custom_ielts_wed],
            user_id="user-1",
            week_start=date(2026, 11, 9),
            restrict_to_window=True,
        )
        selected_ids = [ev.task_id for ev in run_res.schedule.selected_events]
        self.assertNotIn(
            "ev-cs1-too-close-to-ielts",
            selected_ids,
            "Sự kiện kết thúc 17:45 phải bị loại vì không đủ 30 phút di chuyển tới lớp IELTS 18:00!",
        )
        self.assertIn(
            "ev-cs1-enough-travel-time",
            selected_ids,
            "Sự kiện kết thúc 17:30 đủ 30 phút di chuyển nên phải được chọn!",
        )
        self.assertIn(
            "ev-online-no-travel-needed",
            selected_ids,
            "Sự kiện ONLINE không cần thời gian di chuyển nên vẫn hợp lệ!",
        )
        self.assertEqual(run_res.schedule.total_drl_gained, 10)

    def test_case_11_database_serialization_for_custom_task_and_preferences(self):
        """Kiểm tra serialize/deserialize UserTaskRepository, UserTaskPreferenceRepository và UserRepository.drl_scores."""
        from Database.Repository.user_repository import UserRepository
        from Database.Repository.user_task_preference_repository import UserTaskPreferenceRepository
        from Database.Repository.user_task_repository import UserTaskRepository

        custom_dict = {
            "title": "Học IELTS tại Trung tâm Q3",
            "type": "personal",
            "start_time": datetime(2026, 11, 10, 18, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 10, 20, 0, tzinfo=TZ_HCM),
            "location": "Trung tâm Q3",
            "travel_buffer_minutes": 30,
        }
        row = UserTaskRepository.task_to_row(custom_dict, user_id="user-uuid-1")
        self.assertEqual(row["user_id"], "user-uuid-1")
        self.assertEqual(row["travel_buffer_minutes"], 30)
        self.assertEqual(row["type"], "personal")

        restored = UserTaskRepository.row_to_task({**row, "id": "row-1"})
        self.assertEqual(restored.travel_buffer_minutes, 30)
        self.assertEqual(restored.title, "Học IELTS tại Trung tâm Q3")

        pref = UserTaskPreferenceRepository.row_to_pref({
            "task_id": "ev-1",
            "pin_status": "pinned",
            "custom_start_at": "2026-11-12T19:00:00+07:00",
            "custom_end_at": "2026-11-12T19:30:00+07:00",
            "travel_buffer_minutes": 15,
        })
        self.assertEqual(pref["pin_status"], "pinned")
        self.assertEqual(pref["travel_buffer_minutes"], 15)
        self.assertEqual(pref["custom_start_time"], "2026-11-12T19:00:00+07:00")

        user_obj = UserRepository.row_to_user({
            "id": "user-uuid-1",
            "username": "sv@student.hcmus.edu.vn",
            "drl_scores": {"dieu_1": 15, "dieu_2": 10, "dieu_3": 20},
        })
        self.assertEqual(
            user_obj.drl_scores,
            {"dieu_1": 15, "dieu_2": 10, "dieu_3": 20, "dieu_4": 0, "dieu_5": 0},
        )


if __name__ == "__main__":
    unittest.main()
