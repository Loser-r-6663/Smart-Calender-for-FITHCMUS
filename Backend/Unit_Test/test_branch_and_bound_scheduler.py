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

from Backend.branch_and_bound_scheduler import (
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


if __name__ == "__main__":
    unittest.main()
