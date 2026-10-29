"""
Unit Test Suite cho Phân hệ Lập lịch thông minh (Smart Scheduler) - FIT HCMUS.
Sử dụng thư viện chuẩn unittest của Python.

Kiểm chứng 7 trường hợp nghiệp vụ và ràng buộc toán học cốt lõi:
1. test_case_1_hard_anchor_protection: Bảo vệ Thời khóa biểu cố định (không cúp học đi sự kiện ĐRL).
2. test_case_2_campus_travel_constraint: Ràng buộc di chuyển địa lý giữa các cơ sở (CS1 <-> CS2 cần 65p).
3. test_case_3_submodular_category_capping: Ràng buộc trần điểm quy chế 5 Điều (lợi ích biên giảm dần).
4. test_case_4_floating_meals_slotting: Bữa ăn linh hoạt tự động luồn lách giữa ca học sáng và chiều.
5. test_case_5_assignment_feasibility_and_overdue: Phát hiện và cảnh báo bài tập có deadline bất khả thi.
6. test_case_6_sleep_anchor_circadian_rhythm: Bảo vệ giấc ngủ đêm sinh học (23:30 - 06:30, 7 tiếng).
7. test_case_7_online_activity_zero_travel: Hoạt động Online triệt tiêu thời gian di chuyển (D = 0).
"""

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

# Thêm thư mục gốc của dự án vào sys.path để import chuẩn package Backend
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Đảm bảo in tiếng Việt chuẩn UTF-8 trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from Backend.scheduler import (
    ScheduleResult,
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
    TaskStatus,
    TaskType,
)


class TestSchedulerOptimization(unittest.TestCase):
    """Tập hợp các bài kiểm thử đơn vị cho thuật toán lập lịch Google OR-Tools CP-SAT."""

    def setUp(self):
        """Thiết lập môi trường dùng chung trước mỗi ca kiểm thử."""
        # Tuần kiểm thử: Thứ Hai 02/11/2026 -> Chủ Nhật 08/11/2026
        self.week_start = date(2026, 11, 2)
        self.now_dt = datetime(2026, 11, 2, 7, 0, 0)
        self.prefs = UserPreferences(
            campus_travel_minutes=50,
            rest_buffer_minutes=15,
            lunch_duration_minutes=45,
            dinner_duration_minutes=60,
        )

    # -------------------------------------------------------------------------
    # CASE 1: BẢO VỆ THỜI KHÓA BIỂU CỐ ĐỊNH (HARD ANCHOR PROTECTION)
    # -------------------------------------------------------------------------
    def test_case_1_hard_anchor_protection(self):
        """
        Kiểm tra: Khi có sự kiện ĐRL (10 điểm) trùng 100% giờ học lớp Giải tích,
        thuật toán bắt buộc phải ưu tiên việc học và từ chối chọn sự kiện ĐRL.
        """
        class_calculus = Task(
            id="class_calculus",
            title="Vi tích phân 1",
            type=TaskType.CLASS,
            course_code="MTH10001",
            location="CS1",
            start_time=datetime(2026, 11, 2, 7, 30),
            end_time=datetime(2026, 11, 2, 11, 30),
            source_platform=SourcePlatform.PORTAL,
        )
        conflicting_hackathon = Task(
            id="event_hackathon",
            title="Cuộc thi Hackathon (Trùng giờ học)",
            type=TaskType.EVENT,
            location="CS1",
            start_time=datetime(2026, 11, 2, 8, 0),
            end_time=datetime(2026, 11, 2, 11, 0),
            training_points=10,
            drl_category=DRLCategory.DIEU_1,
            source_platform=SourcePlatform.FACEBOOK,
        )

        result = solve_max_drl_schedule(
            tasks=[class_calculus, conflicting_hackathon],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        # Hackathon trùng giờ học nên không được chọn
        self.assertNotIn("event_hackathon", result.selected_event_ids)
        # Tiết học phải tồn tại trong lịch trình
        scheduled_ids = [item.task_id for item in result.scheduled_items]
        self.assertIn("class_calculus", scheduled_ids)

    # -------------------------------------------------------------------------
    # CASE 2: RÀNG BUỘC DI CHUYỂN GIỮA CÁC CƠ SỞ (CAMPUS TRAVEL TIME)
    # -------------------------------------------------------------------------
    def test_case_2_campus_travel_constraint(self):
        """
        Kiểm tra: Học Thể dục tại CS2 kết thúc lúc 10:30.
        Có sự kiện Ngày hội Văn nghệ tại CS1 lúc 11:00 (chỉ cách 30 phút).
        Vì thời gian di chuyển CS2 -> CS1 cần 50p + 15p = 65p > 30p,
        thuật toán bắt buộc phải loại bỏ sự kiện Văn nghệ.
        """
        class_pe_cs2 = Task(
            id="class_pe_cs2",
            title="Thể dục (CS2 Linh Trung)",
            type=TaskType.CLASS,
            location="CS2 - Sân vận động",
            start_time=datetime(2026, 11, 5, 8, 0),
            end_time=datetime(2026, 11, 5, 10, 30),
            source_platform=SourcePlatform.PORTAL,
        )
        event_culture_cs1 = Task(
            id="event_culture_cs1",
            title="Ngày hội Văn nghệ (CS1 Q5)",
            type=TaskType.EVENT,
            location="CS1 - Sân trường",
            start_time=datetime(2026, 11, 5, 11, 0),
            end_time=datetime(2026, 11, 5, 14, 0),
            training_points=5,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        )

        result = solve_max_drl_schedule(
            tasks=[class_pe_cs2, event_culture_cs1],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        # Không kịp di chuyển 65 phút từ Thủ Đức về Q5 nên sự kiện bị loại bỏ
        self.assertNotIn("event_culture_cs1", result.selected_event_ids)

    # -------------------------------------------------------------------------
    # CASE 3: RÀNG BUỘC TRẦN ĐIỂM QUY CHẾ 5 ĐIỀU (SUBMODULAR CAPPING)
    # -------------------------------------------------------------------------
    def test_case_3_submodular_category_capping(self):
        """
        Kiểm tra: Sinh viên đã có 27/30 điểm ở Điều 1 (trần 30, chỉ còn thiếu 3 điểm).
        Có sự kiện Tọa đàm AI trị giá 5 ĐRL ở Điều 1.
        Kỳ vọng: Sự kiện được chọn, nhưng số điểm thực tế ghi nhận chỉ là +3 điểm (không tính khống 5 điểm).
        """
        event_ai = Task(
            id="event_ai_seminar",
            title="Tọa đàm AI",
            type=TaskType.EVENT,
            location="CS1",
            start_time=datetime(2026, 11, 3, 14, 0),
            end_time=datetime(2026, 11, 3, 16, 30),
            training_points=5,
            drl_category=DRLCategory.DIEU_1,
            source_platform=SourcePlatform.FACEBOOK,
        )

        current_points = {
            DRLCategory.DIEU_1.value: 27,  # Còn thiếu 3 điểm
        }

        result = solve_max_drl_schedule(
            tasks=[event_ai],
            week_start=self.week_start,
            now=self.now_dt,
            current_drl_points=current_points,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        self.assertIn("event_ai_seminar", result.selected_event_ids)
        # Điểm thực nhận của Điều 1 chỉ là 3 điểm
        self.assertEqual(result.drl_gained_by_category[DRLCategory.DIEU_1.value], 3)
        self.assertEqual(result.total_drl_gained, 3)

    # -------------------------------------------------------------------------
    # CASE 4: BỮA ĂN LINH HOẠT LUỒN LÁCH GIỮA CÁC CA HỌC (FLOATING MEALS)
    # -------------------------------------------------------------------------
    def test_case_4_floating_meals_slotting(self):
        """
        Kiểm tra: Sinh viên học ca sáng (07:30 - 11:30) và ca chiều (13:00 - 16:30).
        Kỳ vọng: Bữa trưa (45p) tự động được xếp luồn vào khe trống [11:30, 13:00]
        mà không bị đè lên bất kỳ ca học nào.
        """
        morning_class = Task(
            id="class_morning",
            title="Ca học sáng",
            type=TaskType.CLASS,
            location="CS1",
            start_time=datetime(2026, 11, 2, 7, 30),
            end_time=datetime(2026, 11, 2, 11, 30),
            source_platform=SourcePlatform.PORTAL,
        )
        afternoon_class = Task(
            id="class_afternoon",
            title="Ca học chiều",
            type=TaskType.CLASS,
            location="CS1",
            start_time=datetime(2026, 11, 2, 13, 0),
            end_time=datetime(2026, 11, 2, 16, 30),
            source_platform=SourcePlatform.PORTAL,
        )

        result = solve_max_drl_schedule(
            tasks=[morning_class, afternoon_class],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))

        # Tìm bữa trưa của Thứ Hai (ngày 02/11/2026)
        mon_lunch = next(
            (item for item in result.scheduled_items if item.task_id == "lunch_0"),
            None,
        )
        self.assertIsNotNone(mon_lunch, "Bữa trưa Thứ Hai phải được sinh động tạo ra!")
        self.assertEqual(mon_lunch.duration_minutes, 45)
        # Phải diễn ra sau ca sáng (>= 11:30) và kết thúc trước ca chiều (<= 13:00)
        self.assertGreaterEqual(mon_lunch.start_time, datetime(2026, 11, 2, 11, 30))
        self.assertLessEqual(mon_lunch.end_time, datetime(2026, 11, 2, 13, 0))

    # -------------------------------------------------------------------------
    # CASE 5: PHÁT HIỆN BÀI TẬP CÓ DEADLINE BẤT KHẢ THI (ASSIGNMENT FEASIBILITY)
    # -------------------------------------------------------------------------
    def test_case_5_assignment_feasibility_and_overdue(self):
        """
        Kiểm tra:
        - TH1: Bài tập khả thi (cần 2h, deadline còn 2 ngày) -> Xếp lịch thành công.
        - TH2: Bài tập bất khả thi (cần 3h, deadline chỉ còn 30p) -> Solver trả về INFEASIBLE.
        """
        # TH1: Khả thi
        assign_ok = Task(
            id="assign_ok",
            title="Bài tập Lab khả thi",
            type=TaskType.ASSIGNMENT,
            deadline=datetime(2026, 11, 4, 23, 59),
            estimated_hours=2.0,
            source_platform=SourcePlatform.MOODLE,
        )
        result_ok = solve_max_drl_schedule(
            tasks=[assign_ok],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )
        self.assertIn(result_ok.status, ("OPTIMAL", "FEASIBLE"))
        self.assertEqual(len(result_ok.scheduled_assignment_slots), 1)

        # TH2: Bất khả thi (Cần 3 tiếng = 180p, nhưng từ 07:00 đến 07:30 chỉ có 30p)
        assign_impossible = Task(
            id="assign_impossible",
            title="Bài tập quá hạn",
            type=TaskType.ASSIGNMENT,
            deadline=datetime(2026, 11, 2, 7, 30),
            estimated_hours=3.0,
            source_platform=SourcePlatform.MOODLE,
        )
        result_fail = solve_max_drl_schedule(
            tasks=[assign_impossible],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )
        self.assertEqual(result_fail.status, "INFEASIBLE")

    # -------------------------------------------------------------------------
    # CASE 6: BẢO VỆ GIỜ NGỦ BAN ĐÊM (CIRCADIAN SLEEP PROTECTION)
    # -------------------------------------------------------------------------
    def test_case_6_sleep_anchor_circadian_rhythm(self):
        """
        Kiểm tra: Sự kiện ĐRL buổi tối 'Đêm Gala Chào đón Tân sinh viên' kéo dài
        quá khuya (20:00 -> 24:00), lấn 30 phút vào mốc đi ngủ cố định (23:30).
        Kỳ vọng: Khung giờ ngủ 23:30 -> 06:30 là Hard Anchor bất khả xâm phạm,
        thuật toán từ chối chọn sự kiện này để bảo vệ trọn vẹn 7 tiếng ngủ.
        """
        late_night_gala = Task(
            id="event_late_gala",
            title="Đêm Gala Chào đón Tân sinh viên (Kéo dài quá khuya)",
            type=TaskType.EVENT,
            location="CS1 - Hội trường C",
            start_time=datetime(2026, 11, 2, 20, 0),
            end_time=datetime(2026, 11, 3, 0, 0),  # 20:00 đến 24:00 đêm
            training_points=5,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        )

        result = solve_max_drl_schedule(
            tasks=[late_night_gala],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        # Gala kéo dài qua mốc 23:30 nên không được chọn
        self.assertNotIn("event_late_gala", result.selected_event_ids)

        # Kiểm tra giờ ngủ đêm Thứ Hai -> sáng Thứ Ba (sleep_night_0) được bảo vệ trọn vẹn
        sleep_night_0 = next(
            (item for item in result.scheduled_items if item.task_id == "sleep_night_0"),
            None,
        )
        self.assertIsNotNone(sleep_night_0)
        self.assertEqual(sleep_night_0.duration_minutes, 420)  # Đúng 7 tiếng ngủ (420 phút)
        self.assertEqual(sleep_night_0.start_time, datetime(2026, 11, 2, 23, 30))
        self.assertEqual(sleep_night_0.end_time, datetime(2026, 11, 3, 6, 30))

    # -------------------------------------------------------------------------
    # CASE 7: HOẠT ĐỘNG ONLINE TRIỆT TIÊU THỜI GIAN DI CHUYỂN (D = 0)
    # -------------------------------------------------------------------------
    def test_case_7_online_activity_zero_travel(self):
        """
        Kiểm tra: Học tại CS2 (Linh Trung) kết thúc lúc 11:30.
        Sự kiện Webinar Online bắt đầu ngay lúc 11:35 (chỉ cách 5 phút).
        Kỳ vọng: Vì hoạt động trực tuyến qua mạng có thời gian di chuyển D = 0,
        thuật toán vẫn chọn được sự kiện Webinar này mà không báo lỗi di chuyển.
        """
        class_cs2 = Task(
            id="class_cs2",
            title="Học tại Thủ Đức",
            type=TaskType.CLASS,
            location="CS2 - Giảng đường 1",
            start_time=datetime(2026, 11, 4, 8, 0),
            end_time=datetime(2026, 11, 4, 11, 30),
            source_platform=SourcePlatform.PORTAL,
        )
        event_online = Task(
            id="event_online",
            title="Webinar Doanh nghiệp Online",
            type=TaskType.EVENT,
            location="Online - Zoom",
            start_time=datetime(2026, 11, 4, 11, 35),
            end_time=datetime(2026, 11, 4, 12, 35),
            training_points=4,
            drl_category=DRLCategory.DIEU_3,
            source_platform=SourcePlatform.FACEBOOK,
        )

        result = solve_max_drl_schedule(
            tasks=[class_cs2, event_online],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        self.assertIn("event_online", result.selected_event_ids)
        self.assertEqual(result.total_drl_gained, 4)

    # -------------------------------------------------------------------------
    # CASE 8: SỰ KIỆN ĐRL ONLINE CHỈ CÓ END_TIME, KHÔNG CÓ START_TIME
    # -------------------------------------------------------------------------
    def test_case_8_online_drl_event_only_end_time(self):
        """
        Kiểm tra: Sự kiện ĐRL online (vd: Thi trắc nghiệm trực tuyến tìm hiểu quy chế)
        không có start_time cố định, chỉ có end_time đóng cổng nộp bài.
        Kỳ vọng: Thuật toán mô hình hóa thành Optional Flexible Interval, tự động tìm
        khe trống (mặc định 30 phút nếu không truyền estimated_hours) trước end_time
        để xếp vào lịch và cộng điểm ĐRL.
        """
        online_quiz_event = Task(
            id="event_online_quiz",
            title="Thi trắc nghiệm trực tuyến Tìm hiểu Quy chế Công tác Sinh viên",
            type=TaskType.EVENT,
            location="Online - MyAloha",
            start_time=None,  # Không có giờ bắt đầu cố định
            end_time=datetime(2026, 11, 3, 22, 0),  # Chỉ có thời điểm đóng cổng
            training_points=5,
            drl_category=DRLCategory.DIEU_2,
            source_platform=SourcePlatform.PORTAL,
        )

        result = solve_max_drl_schedule(
            tasks=[online_quiz_event],
            week_start=self.week_start,
            now=self.now_dt,
            preferences=self.prefs,
        )

        self.assertIn(result.status, ("OPTIMAL", "FEASIBLE"))
        self.assertIn("event_online_quiz", result.selected_event_ids)
        self.assertEqual(result.total_drl_gained, 5)

        scheduled_quiz = next(
            (item for item in result.scheduled_items if item.task_id == "event_online_quiz"),
            None,
        )
        self.assertIsNotNone(scheduled_quiz)
        self.assertEqual(scheduled_quiz.duration_minutes, 30)  # Mặc định 30 phút
        self.assertGreaterEqual(scheduled_quiz.start_time, self.now_dt)
        self.assertLessEqual(scheduled_quiz.end_time, datetime(2026, 11, 3, 22, 0))


# =============================================================================
# HÀM CHẠY TRỰC TIẾP
# =============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("CHẠY BỘ UNIT TEST TOÀN DIỆN CHO SCHEDULER (GOOGLE OR-TOOLS CP-SAT)")
    print("=" * 80)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSchedulerOptimization)
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)
    if test_result.wasSuccessful():
        print("\n" + "=" * 80)
        print(">>> TẤT CẢ 8/8 UNIT TESTS ĐỀU VƯỢT QUA THÀNH CÔNG (100% PASSED)! <<<")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print(">>> CÓ UNIT TEST THẤT BẠI! <<<")
        print("=" * 80)
        sys.exit(1)
