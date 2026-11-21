# HƯỚNG DẪN TÍNH NĂNG USER INPUT TASK & ĐIỀU CHỈNH LỊCH TRỰC TIẾP

**Hệ thống:** Smart Calendar for FIT-HCMUS  
**Phạm vi tài liệu:** Mô tả luồng cho phép sinh viên **tự thêm công việc cá nhân (kèm thời gian di chuyển ước tính)** và **tương tác điều chỉnh trực tiếp** trên lịch tối ưu do thuật toán Nhánh Cận (Branch & Bound) đề xuất.

---

## 1. TỔNG QUAN LUỒNG TƯƠNG TÁC 2 GIAI ĐOẠN

Để lịch biểu vừa đạt **Điểm Rèn Luyện (ĐRL) tối đa** theo thuật toán, vừa phản ánh đúng **lịch sinh hoạt cá nhân thực tế** của từng sinh viên, hệ thống hoạt động theo vòng lặp 2 giai đoạn:

1. **Giai đoạn 1 — Khởi tạo & Đề xuất Lịch tối ưu ban đầu:**
   * Hệ thống tải lịch học/lịch thi từ Portal, bài tập từ Moodle và danh sách sự kiện ĐRL từ cơ sở dữ liệu (`public.tasks` & `user_tasks`).
   * Thuật toán Nhánh Cận giải bài toán tối ưu lần đầu và in ra báo cáo ĐRL 5 Điều cùng danh sách hoạt động được chọn.
2. **Giai đoạn 2 — Vòng lặp Nhập Task & Điều chỉnh Lịch trực tiếp (`interactive_adjust_schedule`):**
   * Ngay sau khi xem lịch đề xuất, sinh viên có thể thêm việc cá nhân, dời giờ sự kiện linh hoạt, bắt buộc chọn (Pin) hoặc loại bỏ (Reject) một sự kiện bất kỳ.
   * Mỗi lần chỉnh sửa, hệ thống **tự động tái lập lịch trong $< 1\text{ ms}$** để tìm phương án bù điểm tối ưu mới nhất phù hợp với ràng buộc vừa cập nhật.

---

## 2. TÍNH NĂNG 1: USER TỰ THÊM TASK CÁ NHÂN (`create_custom_task`)

Sinh viên có thể chủ động nhập thêm 3 loại công việc cá nhân không có sẵn trên Portal/Moodle thông qua hàm `create_custom_task(...)` hoặc lựa chọn **`[1]`** trên menu:

### 2.1. Phân loại Task cá nhân
| Loại Task | Giá trị `type` | Cách thuật toán xử lý |
|---|---|---|
| **Lịch bận cố định** | `personal` / `class` | Đưa thẳng vào tập **`FixedIntervals` (Hard Anchors)**. Chặn toàn bộ sự kiện ĐRL trùng giờ và kiểm tra đệm di chuyển. |
| **Bài tập / Tự học linh hoạt** | `assignment` | Đưa vào tập **`FlexibleWorkloads`**. Tầng 4 (Tier 4 Slack Pruning) sẽ bảo toàn đủ `estimated_hours` (mặc định `3.5h`) giờ rảnh trong khoảng thời gian mở để sinh viên kịp làm bài. |
| **Sự kiện ĐRL tự thêm** | `event` (`training_points > 0`) | Đưa vào lịch với vai trò hoạt động có điểm ĐRL (tự động ghim vào lịch và cộng điểm vào Điều tương ứng 1–5). |

### 2.2. Cơ chế Thời gian di chuyển ước tính (`travel_buffer_minutes`)
* **Vấn đề thực tế:** Các sự kiện của trường chỉ diễn ra ở `CS1` (Quận 5), `CS2` (Thủ Đức) hoặc `ONLINE`, nên quy tắc đệm mặc định (`60` phút giữa `CS1 <-> CS2`, `0` phút nếu cùng cơ sở) là đủ. Tuy nhiên, các lịch cá nhân bên ngoài trường (học IELTS ở Quận 3, đi làm thêm, dạy gia sư...) có khoảng cách di chuyển rất khác nhau.
* **Giải pháp:** Khi nhập Task cá nhân, user có thể điền **`travel_buffer_minutes`** (số phút di chuyển ước tính, VD: `20`, `30`, `45` phút).
* **Quy tắc tính đệm `get_travel_buffer_minutes(A, B)`:**
  1. Nếu $A$ hoặc $B$ là **`ONLINE`** $\implies$ **Đệm = `0` phút** (vì hoạt động online có thể tham gia tại chỗ).
  2. Nếu cả $A$ và $B$ đều là **Offline** ở khác địa điểm và có khai báo `travel_buffer_minutes` $\implies$ dùng đúng khoảng đệm lớn hơn giữa hai hoạt động:
     $$\text{Buffer}(A, B) = \max\big(\text{travel\_buffer}_A, \; \text{travel\_buffer}_B\big)$$
  3. Nếu cả hai đều không khai báo riêng $\implies$ áp dụng quy tắc mặc định của trường (`60` phút khi `CS1 != CS2`, `0` phút khi cùng cơ sở).
* **Ví dụ minh họa:**
  * Sinh viên thêm lịch *"Học IELTS tại Trung tâm Q3"* từ **`18:00 -> 20:00`** với **`travel_buffer_minutes = 30`**.
  * Sự kiện ĐRL tại `CS1` kết thúc lúc **`17:45`** $\rightarrow$ khoảng trống chỉ có **15 phút** (`< 30 phút`) $\implies$ **Bị loại** để đảm bảo sinh viên kịp chạy tới lớp IELTS.
  * Sự kiện ĐRL tại `CS1` kết thúc lúc **`17:30`** $\rightarrow$ khoảng trống đủ **30 phút** $\implies$ **Hợp lệ**.
  * Sự kiện ĐRL **`ONLINE`** kết thúc lúc **`17:55`** $\rightarrow$ không cần di chuyển (`0` phút) $\implies$ **Hợp lệ**.
* Ngoài ra, trong quá trình tính **Tier 4 (Flexible Workload Slack Pruning)**, thời gian bận của các task cố định cũng được nới rộng thêm `±travel_buffer_minutes` để phản ánh chính xác quỹ giờ rảnh thực tế trong ngày.

---

## 3. TÍNH NĂNG 2: ĐIỀU CHỈNH TRỰC TIẾP TRÊN LỊCH ĐÃ XUẤT (`interactive_adjust_schedule`)

Sau khi chạy thuật toán, người dùng tương tác qua **Menu điều chỉnh trực tiếp** trong `Backend/Scheduling/service.py` (được tích hợp sẵn khi chạy `user.py`):

### Thao tác `[1]` — Thêm Task cá nhân mới
* Nhập tên công việc, chọn loại (`1`: Lịch bận cố định, `2`: Bài tập linh hoạt, `3`: Sự kiện ĐRL tự thêm), thời gian bắt đầu/kết thúc (hỗ trợ định dạng linh hoạt `DD/MM HH:MM`, `YYYY-MM-DD HH:MM` hoặc `HH:MM`), địa điểm và `travel_buffer_minutes`.
* Hệ thống lập tức đưa task vào dữ liệu và giải lại B&B.

### Thao tác `[2]` — Đổi khung giờ hoạt động trên lịch (`Reschedule`)
* **Mục đích:** Với các sự kiện ĐRL online linh hoạt (khảo sát, quiz mở cả tuần), thuật toán tự động xếp vào một khung giờ rảnh mặc định (`08:00 -> 22:00`). User có thể dời sang khung giờ thuận tiện hơn (VD: dời từ sáng Thứ 2 sang `20:00` tối Thứ 4).
* **Cách xử lý:**
  * Hệ thống gán `custom_start_time`, `custom_end_time` và đặt `pin_status = "pinned"` cho sự kiện đó.
  * Tự động bật cờ `_has_custom_time = True` để khóa cứng sự kiện vào đúng khung giờ mới user chọn (không tự động phân bổ lại nữa), đồng thời cảnh báo nếu khung giờ mới vượt ra ngoài thời hạn mở (`window_start` $\rightarrow$ `window_end`) của sự kiện.

### Thao tác `[3]` — Ghim / Bắt buộc tham gia (`Pin`)
* **Mục đích:** Danh sách kết quả trả về thêm `unselected_events` — các sự kiện ĐRL khả thi trong tuần nhưng không được chọn (thường vì trùng giờ với sự kiện khác hoặc dư điểm). Nếu sinh viên vẫn muốn đi một sự kiện cụ thể trong số này, chọn **Pin**.
* **Cách xử lý:** Đặt `pin_status = "pinned"`. Thuật toán khóa trước sự kiện này vào lịch, cộng trước điểm ĐRL của nó vào `curr_drl`, đồng thời đưa vào `fixed_intervals` (nếu cố định giờ) hoặc `flexible_workloads` (nếu linh hoạt) rồi chạy lại B&B để tối ưu phần thời gian còn lại xung quanh sự kiện đã ghim.

### Thao tác `[4]` — Loại bỏ hoạt động khỏi lịch (`Reject`)
* **Mục đích:** Nếu lịch gợi ý một sự kiện ĐRL mà sinh viên không muốn tham gia, chọn **Reject**.
* **Cách xử lý:** Đặt `pin_status = "rejected"` (hoặc xóa khỏi `custom_tasks` nếu là task tự thêm). Thuật toán loại bỏ sự kiện này và ngay lập tức tìm phương án thay thế tối ưu nhất vào khoảng trống vừa giải phóng.

### Thao tác `[5]` — Xem Lịch biểu tổng hợp cả tuần (`print_full_weekly_timetable`)
* In toàn bộ dòng thời gian sắp xếp theo thứ tự thời gian trong tuần, bao gồm:
  * Lịch học & lịch thi (`[CLASS]`, `[EXAM]`)
  * Task cá nhân (`[PERSONAL]`, kèm ghi chú `Di chuyển: ±Xp` nếu có)
  * Các hoạt động ĐRL được chọn (kèm nhãn `[Linh hoạt]` / `[Đã ghim]` và điểm cộng)
  * Danh sách các bài tập/nhiệm vụ linh hoạt đang được bảo vệ quỹ giờ tự học ở Tầng 4.

---

## 4. CÁC FILE MÃ NGUỒN LIÊN QUAN

| File | Vai trò |
|---|---|
| `Backend/Scheduling/branch_and_bound_models.py` | Định nghĩa `ScheduledDRLEvent`, `BranchAndBoundResult` (chứa `unselected_events`, `fixed_tasks_summary`, `flexible_tasks_summary`) và hàm `get_travel_buffer_minutes(...)` hỗ trợ `travel_buffer_minutes`. |
| `Backend/Scheduling/branch_and_bound_scheduler.py` | Xử lý `pin_status` (`pinned`/`rejected`), `_has_custom_time`, nới rộng khoảng đệm di chuyển trong `is_workload_feasible` và kiểm tra xung đột. |
| `Backend/Scheduling/service.py` | Cung cấp `create_custom_task(...)`, `custom_tasks`, `user_task_prefs`, `print_full_weekly_timetable(...)` và vòng lặp menu `interactive_adjust_schedule(...)`. |
| `user.py` | Điểm khởi chạy chính cho người dùng, tự động mở menu điều chỉnh tương tác sau khi xuất lịch tối ưu. |
| `Backend/Unit_Test/test_branch_and_bound_scheduler.py` | Bộ Unit Test gồm `test_case_9` (pin/reject/custom time) và `test_case_10` (custom task kèm `travel_buffer_minutes`). |
