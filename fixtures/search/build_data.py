"""Reproduce the curated JSON files; expectations below are hand-authored."""
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLOCK = "2026-10-30T12:00:00+07:00"


def ts(day, time="17:00:00"):
    return f"2026-{day}T{time}+07:00"


def task(id, title, kind, description, **values):
    row = dict(id=id, title=title, type=kind, course_code=None,
               description=description, target_audience="FIT students", location="Online",
               registration_start=None, registration_end=None, start_time=None,
               end_time=None, deadline=None, estimated_hours=None, training_points=0,
               drl_category=None, recurrence="NONE", status="active", is_manual=False,
               source_url=f"https://fixtures.example.invalid/{id}",
               source_platform="portal", embedding=None, updated_at=ts("10-20"))
    row.update(values)
    return row


def assignment(id, title, course, day, description, **values):
    return task(id, title, "assignment", description, course_code=course,
                deadline=ts(day, "23:59:00"), estimated_hours=3.0,
                source_platform="moodle", **values)


def event(id, title, description, day="11-02", **values):
    row = task(id, title, "event", description,
               start_time=ts(day, "08:00:00"), end_time=ts(day, "10:00:00"),
               registration_start=ts("10-20", "08:00:00"), registration_end=ts("10-31"),
               training_points=5, drl_category="dieu_3", source_platform="facebook")
    row.update(values)
    return row


TASKS = [
    assignment("asg-csc10004-lab", "CSC10004 Lab 3: Cấu trúc dữ liệu", "CSC10004", "10-30", "Nộp bài thực hành danh sách liên kết."),
    assignment("asg-csc10005-lab", "CSC10005 Lab 3: Kỹ thuật lập trình", "CSC10005", "10-30", "Nộp bài thực hành con trỏ."),
    assignment("asg-csc10004-project", "CSC10004 Search project", "CSC10004", "11-06", "Implement an index and submit a report."),
    assignment("asg-csc10005-project", "CSC10005 Search project", "CSC10005", "11-06", "Submit a programming report."),
    assignment("asg-ct-proposal", "Đề cương đồ án Computational Thinking", "CSC10014", "11-01", "Upload team proposal and decomposition."),
    assignment("asg-db-sql", "Database SQL homework", "CSC10006", "11-03", "Practice joins and aggregation."),
    assignment("asg-network", "Bài tập Mạng máy tính", "CSC10008", "10-31", "Phân tích gói tin và báo cáo."),
    assignment("asg-english", "English presentation slides", "ENG10001", "11-04", "Prepare a talk about university life."),
    assignment("asg-done", "CSC10004 Lab 2 completed", "CSC10004", "10-29", "Bài đã nộp.", status="done"),
    assignment("asg-cancelled", "CSC10005 Lab 2 cancelled", "CSC10005", "10-29", "Bài đã hủy.", status="cancelled"),
    assignment("asg-archived", "Archived calculus worksheet", "MTH10001", "10-01", "Previous worksheet.", status="archived"),
    assignment("asg-update", "Bản nháp đồ án", "CSC10014", "10-30", "Đề cương cần chỉnh sửa."),
    task("fee-hk1", "Học phí HK1 năm 2026", "tuition", "Thông báo đóng học phí cho sinh viên FIT.", deadline=ts("11-15")),
    task("fee-installment", "Gia hạn học phí đợt 2", "tuition", "Học phí được chia thành hai đợt.", deadline=ts("11-20"), target_audience="K26"),
    task("fee-english", "Tuition payment notice", "tuition", "Semester fee payment instructions.", deadline=ts("11-10")),
    task("fee-mixed", "Học phí scholarship adjustment", "tuition", "Kiểm tra tuition balance sau học bổng.", deadline=ts("11-12"), target_audience="K25"),
    task("fee-done", "Học phí đã hoàn tất", "tuition", "Thông báo đã xử lý.", deadline=ts("10-25"), status="done"),
    event("evt-reg-before", "Đăng ký workshop Python sáng", "Đóng đơn lúc 11 giờ hôm nay.", registration_end=ts("10-30", "11:00:00")),
    event("evt-reg-exact", "Đăng ký workshop Python trưa", "Đóng đơn đúng 12 giờ hôm nay.", registration_end=CLOCK),
    event("evt-reg-after", "Đăng ký workshop Python chiều", "Đóng đơn lúc 13 giờ hôm nay.", registration_end=ts("10-30", "13:00:00")),
    event("evt-overlap", "Triển lãm công nghệ ba ngày", "Trải nghiệm sản phẩm sinh viên từ hôm qua đến ngày mai.", day="10-29", end_time=ts("10-31", "18:00:00"), registration_end=ts("10-28"), location="CS2 - Hall A"),
    event("evt-today", "Career talk hôm nay", "Gặp gỡ nhà tuyển dụng.", day="10-30", registration_end=ts("10-29"), location="CS2 - Hall A"),
    event("evt-missing-start", "Robotics meetup", "Chưa công bố ngày mở đơn.", registration_start=None),
    event("evt-missing-end", "AI reading group", "Chưa công bố hạn đăng ký.", registration_end=None),
    event("evt-missing-both", "Community coding circle", "Chưa có lịch đăng ký.", registration_start=None, registration_end=None),
    event("evt-green", "Chủ nhật xanh", "Dọn rác và trồng cây ở khuôn viên CS2.", day="11-01", location="CS2 - Campus garden", training_points=7),
    event("evt-beach", "Coastal cleanup day", "Collect litter along the beach with the student volunteer club.", day="11-08", location="Can Gio", training_points=10),
    event("evt-speaking", "Speak with confidence", "Practice presenting ideas to an audience; feedback from peers.", target_audience="K26", location="CS1 - Room F101", drl_category="dieu_1"),
    event("evt-debate", "Tranh biện song ngữ", "Thuyết trình và phản biện bằng tiếng Việt, tiếng Anh.", target_audience="K26", location="CS1 - Room F101", training_points=3),
    event("evt-cancelled", "Workshop AI đã hủy", "Không tổ chức theo kế hoạch.", status="cancelled"),
    event("evt-done", "Workshop AI đã hoàn thành", "Hoạt động đã kết thúc.", day="10-24", registration_end=ts("10-23"), status="done"),
    event("evt-cancel", "Security seminar", "Introduction to secure programming."),
    event("evt-delete", "Chess evening", "Friendly student chess games.", training_points=0, drl_category=None),
    event("evt-future-reg", "Hackathon winter", "Registration starts tomorrow.", day="11-10", registration_start=ts("10-31", "08:00:00"), registration_end=ts("11-05")),
    event("evt-end-midnight", "Đêm lập trình", "Kết thúc đúng đầu ngày 30.", day="10-29", end_time=ts("10-30", "00:00:00"), registration_end=ts("10-28")),
    event("evt-next-midnight", "Midnight code camp", "Starts at the beginning of October 31.", day="10-31", start_time=ts("10-31", "00:00:00"), registration_end=ts("10-29")),
    task("class-csc10004", "CSC10004 lecture", "class", "Weekly lecture, one materialized occurrence.", course_code="CSC10004", start_time=ts("10-30", "07:30:00"), end_time=ts("10-30", "11:00:00"), location="CS1 - Room F102", recurrence="WEEKLY:FRI"),
    task("exam-csc10005", "CSC10005 midterm", "exam", "Bring student card; synthetic notice.", course_code="CSC10005", start_time=ts("11-07", "09:00:00"), end_time=ts("11-07", "10:30:00"), location="CS2 - Room B201"),
    task("personal-study", "Ôn tập tự chọn", "personal", "Review notes independently.", start_time=ts("10-30", "19:00:00"), end_time=ts("10-30", "20:00:00"), is_manual=True, source_platform="custom"),
    assignment("asg-overdue", "CSC10004 Lab 1 overdue", "CSC10004", "10-28", "Chưa nộp; vẫn active dù đã quá hạn."),
]

DAY = [ts("10-30", "00:00:00"), ts("10-31", "00:00:00")]
QUERIES = []


def query(id, text, mode, expected, rationale, tags, filters=None, keyword=None,
          state="base", at=CLOCK, exclude=None, grades=None):
    row = dict(id=id, text=text, mode=mode, evaluation="retrieval", state=state,
               reference_time=at, request={"filters": filters or {}},
               ordering_required=False, rationale=rationale, coverage_tags=tags,
               excluded_ids=exclude or [])
    if keyword is not None:
        row["request"]["keyword"] = keyword
    if grades is None:
        row["expected_ids"] = expected
    else:
        row["relevance_labels"] = grades
        row["unlisted_eligible_grade"] = 0
        row["request"]["semantic_text"] = text
    QUERIES.append(row)


query("q01", "CSC10004 assignments", "structured", ["asg-csc10004-lab", "asg-csc10004-project", "asg-overdue"], "Exact course and type, including overdue active work.", ["course-isolation", "overdue"], {"course_code": "CSC10004", "types": ["assignment"]}, exclude=["asg-csc10005-lab", "asg-csc10005-project"])
query("q02", "Search project môn CSC10005", "hybrid", ["asg-csc10005-project"], "Lexical hybrid branch with a hard course constraint; no semantic branch requested.", ["course-isolation", "mixed-language"], {"course_code": "CSC10005"}, "Search project", exclude=["asg-csc10004-project"])
query("q03", "học phí", "keyword", ["fee-hk1", "fee-installment", "fee-mixed"], "All normalized tokens must occur; no English translation.", ["accent-equivalence"], keyword="học phí")
query("q04", "hoc phi", "keyword", ["fee-hk1", "fee-installment", "fee-mixed"], "Same tokens after Vietnamese accent folding.", ["accent-equivalence"], keyword="hoc phi")
query("q05", "Registration closes today", "structured", ["evt-reg-before", "evt-reg-exact", "evt-reg-after"], "Closing today is a date test, including already closed registrations.", ["closes-today"], {"types": ["event"], "registration_end_within": DAY})
query("q06", "Python registration open now", "hybrid", ["evt-reg-exact", "evt-reg-after"], "11:00 is closed, 12:00 inclusive, 13:00 still open.", ["registration-boundary", "before-exact-after"], {"registration_open_at": CLOCK}, "Python", exclude=["evt-reg-before"])
query("q07", "Python registration at 11:59:59", "hybrid", ["evt-reg-exact", "evt-reg-after"], "One second before the noon closing instant.", ["registration-boundary"], {"registration_open_at": ts("10-30", "11:59:59")}, "Python", at=ts("10-30", "11:59:59"))
query("q08", "Python registration at 12:00:01", "hybrid", ["evt-reg-after"], "One second after noon removes the noon workshop.", ["registration-boundary"], {"registration_open_at": ts("10-30", "12:00:01")}, "Python", at=ts("10-30", "12:00:01"), exclude=["evt-reg-exact"])
query("q09", "Events overlapping today", "structured", ["evt-overlap", "evt-today"], "Half-open intervals include spanning events, exclude midnight touching.", ["overlap", "day-boundary"], {"types": ["event"], "event_overlaps": DAY}, exclude=["evt-end-midnight", "evt-next-midnight"])
query("q10", "Events starting today", "structured", ["evt-today"], "Starts-within is narrower than overlap.", ["starts-within"], {"types": ["event"], "start_time_within": DAY}, exclude=["evt-overlap"])
query("q11", "Robotics registration definitely open", "hybrid", [], "Missing registration start is unknown.", ["missing-start"], {"registration_open_at": CLOCK}, "Robotics", exclude=["evt-missing-start"])
query("q12", "AI reading registration definitely open", "hybrid", [], "Missing registration end is unknown.", ["missing-end"], {"registration_open_at": CLOCK}, "AI reading", exclude=["evt-missing-end"])
query("q13", "Coding circle registration definitely open", "hybrid", [], "Both registration endpoints are unknown.", ["missing-both"], {"registration_open_at": CLOCK}, "coding circle", exclude=["evt-missing-both"])
query("q14", "Workshop AI", "keyword", [], "Default active-only policy hides cancelled and done tasks.", ["status-default"], keyword="Workshop AI", exclude=["evt-cancelled", "evt-done"])
query("q15", "Cancelled AI workshop", "keyword", ["evt-cancelled"], "Explicit status replaces the active default.", ["status-cancelled"], {"statuses": ["cancelled"]}, "Workshop AI")
query("q16", "Completed AI workshop", "keyword", ["evt-done"], "Completed is represented by the existing done value.", ["status-done"], {"statuses": ["done"]}, "Workshop AI")
query("q17", "quantum pineapple", "keyword", [], "No relevant token match; no active-task fallback.", ["negative"], keyword="quantum pineapple")
query("q18", "quantum pineapple CSC10004", "hybrid", [], "A course filter does not justify fallback on keyword miss.", ["negative", "course-isolation"], {"course_code": "CSC10004"}, "quantum pineapple")
query("q19", "Tuition deadlines in November before the 16th", "structured", ["fee-hk1", "fee-english", "fee-mixed"], "Filter the payment deadline, not registration or event times.", ["tuition", "deadline-role"], {"types": ["tuition"], "deadline_within": [ts("11-01", "00:00:00"), ts("11-16", "00:00:00")]})
query("q20", "CS2 events worth at least 5 points today", "structured", ["evt-overlap", "evt-today"], "Combines location, minimum points, type and overlap.", ["combined-filters", "training-points"], {"types": ["event"], "location_prefix": "CS2", "min_training_points": 5, "event_overlaps": DAY})
query("q21", "Upcoming environmental volunteering", "semantic", None, "Green campus cleanup and coastal litter collection directly address this intent; coding is unrelated.", ["semantic", "environment"], {"types": ["event"], "start_time_within": [ts("10-31", "00:00:00"), ts("11-10", "00:00:00")]}, grades={"evt-green": 2, "evt-beach": 2})
query("q22", "Activities for K26 to improve public speaking", "semantic", None, "Presentation practice directly fits; bilingual debate practices related communication skills.", ["semantic", "audience"], {"types": ["event"], "target_audience": "K26"}, grades={"evt-speaking": 2, "evt-debate": 1})
query("q23", "CSC10004 Moodle work due today", "structured", ["asg-csc10004-lab"], "Course, source, type and due-date intersection.", ["combined-filters", "source", "deadline-role"], {"course_code": "CSC10004", "types": ["assignment"], "source_platform": "moodle", "deadline_within": DAY})
query("q24", "Archived worksheets", "structured", ["asg-archived"], "Explicit archived status is supported independently of current dates.", ["status-archived"], {"statuses": ["archived"]})
query("q25", "Bản nháp", "keyword", ["asg-update"], "Old title is searchable before the edit.", ["update-title"], keyword="Bản nháp")
query("q26", "Bản nháp after edit", "keyword", [], "Old title must leave every retrieval index.", ["update-title"], keyword="Bản nháp", state="edited", exclude=["asg-update"])
query("q27", "CSC10014 due today", "structured", ["asg-update"], "Original deadline lies today.", ["update-deadline"], {"course_code": "CSC10014", "deadline_within": DAY})
query("q28", "Final retrieval report due November 2", "hybrid", ["asg-update"], "New title and deadline belong to the same stable ID.", ["update-deadline", "update-title"], {"course_code": "CSC10014", "deadline_within": [ts("11-02", "00:00:00"), ts("11-03", "00:00:00")]}, "Final retrieval", state="edited")
query("q29", "Security seminar", "keyword", ["evt-cancel"], "Active before cancellation.", ["cancel-operation"], keyword="Security seminar")
query("q30", "Security seminar after cancellation", "keyword", [], "Cancelled records disappear from default results.", ["cancel-operation"], keyword="Security seminar", state="cancelled", exclude=["evt-cancel"])
query("q31", "Chess evening", "keyword", ["evt-delete"], "Present before explicit deletion.", ["delete-operation"], keyword="Chess evening")
query("q32", "Chess evening after deletion", "keyword", [], "Deleted records cannot survive in any retrieval index.", ["delete-operation"], keyword="Chess evening", state="deleted", exclude=["evt-delete"])

SCENARIOS = [
    dict(id="edited", from_state="base", operation="update", task_id="asg-update",
         reference_time=CLOCK, changes=dict(title="Final retrieval report", deadline=ts("11-02", "23:59:00"), updated_at=CLOCK),
         before_queries=["q25", "q27"], after_queries=["q26", "q28"]),
    dict(id="cancelled", from_state="base", operation="update", task_id="evt-cancel",
         reference_time=CLOCK, changes=dict(status="cancelled", updated_at=CLOCK), before_queries=["q29"], after_queries=["q30"]),
    dict(id="deleted", from_state="base", operation="delete", task_id="evt-delete",
         reference_time=CLOCK, before_queries=["q31"], after_queries=["q32"]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check byte-for-byte reproducibility without writing")
    args = parser.parse_args()
    for name, data in (("tasks", TASKS), ("queries", QUERIES), ("scenarios", SCENARIOS)):
        path = ROOT / f"{name}.json"
        content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if args.check:
            if path.read_bytes() != content:
                raise SystemExit(f"Not reproducible: {path.name}; regenerate with build_data.py")
        else:
            path.write_bytes(content)
    if args.check:
        print("Reproducibility check passed for tasks.json, queries.json and scenarios.json.")


if __name__ == "__main__":
    main()
