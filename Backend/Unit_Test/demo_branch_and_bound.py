"""
Demo Lập lịch Tối ưu Điểm Rèn Luyện (ĐRL) bằng Thuật toán Nhánh Cận (Branch and Bound).
Mô phỏng thực tế tuần sinh viên FIT - HCMUS (02/11/2026 -> 08/11/2026):
- Dữ liệu đầu vào chuẩn hóa 100% theo Schema bảng tasks của PostgreSQL Database.
- Tự động lọc qua lịch học cố định và thời gian di chuyển giữa 2 cơ sở (CS1 <-> CS2).
- Áp dụng Mô hình Trần Kép (Double Capping):
  + Trần 5 Tiêu chí thành phần: Điều 1 (30đ), Điều 2 (20đ), Điều 3 (25đ), Điều 4 (25đ), Điều 5 (30đ).
  + Trần toàn cục tối đa 100 điểm theo Quy chế ĐHKHTN (Global Cap = 100).
- Cơ chế Dừng sớm (Early Stopping): Khi sinh viên đã đủ 100 điểm, thuật toán dừng chọn thêm sự kiện,
  bảo vệ trọn vẹn quỹ thời gian nghỉ ngơi cuối tuần cho sinh viên.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from Backend.Scheduling.branch_and_bound_scheduler import BranchAndBoundScheduler


TZ_HCM = timezone(timedelta(hours=7))


def main():
    # -------------------------------------------------------------------------
    # 1. DỮ LIỆU ĐẦU VÀO MÔ PHỎNG TỪ BẢNG TASKS TRONG POSTGRESQL DATABASE
    # -------------------------------------------------------------------------
    tasks_from_database = [
        # --- A. LỊCH HỌC TẬP CỐ ĐỊNH TRONG TUẦN (TKB TỪ PORTAL) ---
        {
            "id": "tkb-mon-1",
            "title": "Vi tích phân 1B (Lý thuyết)",
            "type": "class",
            "course_code": "MTH10001",
            "start_time": datetime(2026, 11, 2, 7, 30, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 2, 11, 30, tzinfo=TZ_HCM),
            "location": "CS1 - Giảng đường F201",
            "training_points": 0,
            "status": "active",
        },
        {
            "id": "tkb-tue-1",
            "title": "Nhập môn Lập trình (Thực hành)",
            "type": "class",
            "course_code": "CSC10001",
            "start_time": datetime(2026, 11, 3, 13, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 3, 16, 30, tzinfo=TZ_HCM),
            "location": "CS2 - Phòng máy Linh Trung",
            "training_points": 0,
            "status": "active",
        },
        {
            "id": "tkb-wed-1",
            "title": "Mạng máy tính (Lý thuyết)",
            "type": "class",
            "course_code": "CSC10004",
            "start_time": datetime(2026, 11, 4, 7, 30, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 4, 11, 30, tzinfo=TZ_HCM),
            "location": "CS1 - Giảng đường C",
            "training_points": 0,
            "status": "active",
        },
        {
            "id": "tkb-thu-1",
            "title": "Giáo dục thể chất (Bóng chuyền)",
            "type": "class",
            "course_code": "PHE10001",
            "start_time": datetime(2026, 11, 5, 8, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 5, 10, 30, tzinfo=TZ_HCM),
            "location": "CS2 - Nhà thi đấu Thủ Đức",
            "training_points": 0,
            "status": "active",
        },
        {
            "id": "tkb-fri-1",
            "title": "Cấu trúc dữ liệu và Giải thuật",
            "type": "class",
            "course_code": "CSC10002",
            "start_time": datetime(2026, 11, 6, 13, 30, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 6, 17, 0, tzinfo=TZ_HCM),
            "location": "CS1 - Phòng I42",
            "training_points": 0,
            "status": "active",
        },
        {
            "id": "personal-sat",
            "title": "Học tiếng Anh IELTS định kỳ",
            "type": "personal",
            "start_time": datetime(2026, 11, 7, 8, 30, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 7, 11, 0, tzinfo=TZ_HCM),
            "location": "CS1 - Quận 5",
            "training_points": 0,
            "status": "active",
        },

        # --- B. DANH SÁCH SỰ KIỆN CÓ CỘNG ĐRL TRONG TUẦN (CÀO TỪ FACEBOOK, CTSV, MOODLE) ---
        {
            "id": "event-1",
            "title": "Tọa đàm Khoa học: Generative AI & Tương lai ngành CNTT",
            "type": "event",
            "start_time": datetime(2026, 11, 3, 8, 30, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 3, 11, 30, tzinfo=TZ_HCM),
            "location": "CS2 - Hội trường Linh Trung",
            "training_points": 5,
            "drl_category": "dieu_1",
            "status": "active",
        },
        {
            "id": "event-2-clash-class",
            "title": "Cuộc thi Lập trình HCMUS Hackathon (Trùng lịch học Mạng MT)",
            "type": "event",
            "start_time": datetime(2026, 11, 4, 8, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 4, 11, 0, tzinfo=TZ_HCM),
            "location": "CS1 - Tòa F",
            "training_points": 10,
            "drl_category": "dieu_1",
            "status": "active",
        },
        {
            "id": "event-3",
            "title": "Buổi phổ biến Quy chế Học vụ & Chính sách Học bổng",
            "type": "event",
            "start_time": datetime(2026, 11, 4, 14, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 4, 16, 30, tzinfo=TZ_HCM),
            "location": "CS1 - Hội trường I",
            "training_points": 5,
            "drl_category": "dieu_1",
            "status": "active",
        },
        {
            "id": "event-4-travel-clash",
            "title": "Ngày hội Thể thao Đoàn Khoa FIT (Không kịp chạy xe từ CS2 về CS1 trong 60 phút)",
            "type": "event",
            "start_time": datetime(2026, 11, 5, 11, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 5, 13, 30, tzinfo=TZ_HCM),
            "location": "CS1 - Sân trường Q5",
            "training_points": 8,
            "drl_category": "dieu_3",
            "status": "active",
        },
        {
            "id": "event-5",
            "title": "Ngày hội Hiến máu Tình nguyện Giọt hồng Yêu thương",
            "type": "event",
            "start_time": datetime(2026, 11, 6, 8, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 6, 11, 0, tzinfo=TZ_HCM),
            "location": "CS1 - Sảnh tòa nhà C",
            "training_points": 8,
            "drl_category": "dieu_4",
            "status": "active",
        },
        {
            "id": "event-6",
            "title": "Webinar Kỹ năng viết CV & Phỏng vấn Thực tập sinh IT",
            "type": "event",
            "start_time": datetime(2026, 11, 7, 14, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 7, 16, 30, tzinfo=TZ_HCM),
            "location": "Online - MS Teams",
            "training_points": 4,
            "drl_category": "dieu_3",
            "status": "active",
        },
        {
            "id": "event-7",
            "title": "Chiến dịch Chủ Nhật Xanh - Bảo vệ Môi trường Đô thị",
            "type": "event",
            "start_time": datetime(2026, 11, 8, 8, 0, tzinfo=TZ_HCM),
            "end_time": datetime(2026, 11, 8, 11, 0, tzinfo=TZ_HCM),
            "location": "CS2 - Khu đô thị ĐHQG-HCM",
            "training_points": 6,
            "drl_category": "dieu_4",
            "status": "active",
        },
        {
            "id": "event-8-online-deadline",
            "title": "Thi trắc nghiệm trực tuyến Tìm hiểu Nội quy & Quy chế Nhà trường",
            "type": "event",
            "deadline": datetime(2026, 11, 5, 22, 0, tzinfo=TZ_HCM),
            "location": "Online - MyAloha",
            "training_points": 3,
            "drl_category": "dieu_2",
            "status": "active",
        },
    ]

    # -------------------------------------------------------------------------
    # 2. KHỞI TẠO BỘ LẬP LỊCH & THỰC THI THUẬT TOÁN NHÁNH CẬN
    # -------------------------------------------------------------------------
    # Mặc định global_cap=100 (Trần toàn cục tối đa 100 điểm theo Quy chế ĐHKHTN)
    scheduler = BranchAndBoundScheduler(campus_travel_minutes=60, global_cap=100)

    # Điểm rèn luyện hiện có của sinh viên theo 5 Điều (Tổng hiện có: 82 điểm)
    # Mục tiêu tối đa: Sinh viên chỉ cần thêm đúng 18 điểm để chạm mốc tuyệt đối 100 điểm
    initial_drl = {
        "dieu_1": 22,  # Học tập & NCKH: 22/30đ (còn thiếu 8đ để chạm trần 30đ)
        "dieu_2": 17,  # Chấp hành nội quy, quy chế: 17/20đ (chỉ còn thiếu 3đ để chạm trần 20đ)
        "dieu_3": 18,  # Chính trị - xã hội, văn thể mỹ: 18/25đ
        "dieu_4": 15,  # Hành động hướng đến cộng đồng: 15/25đ
        "dieu_5": 10,  # Các nội dung khuyến khích: 10/30đ
    }

    result = scheduler.schedule(tasks_from_database, initial_drl=initial_drl)

    # -------------------------------------------------------------------------
    # 3. XUẤT BÁO CÁO KẾT QUẢ TRỰC QUAN
    # -------------------------------------------------------------------------
    result.print_summary()


if __name__ == "__main__":
    main()
