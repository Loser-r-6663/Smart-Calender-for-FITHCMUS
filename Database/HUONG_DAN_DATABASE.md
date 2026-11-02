# Tài liệu cơ sở dữ liệu và hướng dẫn sử dụng

Tài liệu này mô tả cấu trúc PostgreSQL, cách cấu hình kết nối và cách sử dụng
REST API để thao tác với database của Smart Calendar.

## 1. Thành phần

- `Db_query.sql`: tạo các bảng, khóa ngoại, ràng buộc và chỉ mục.
- `db_connection.py`: đọc cấu hình từ `.env`, tạo kết nối và quản lý transaction.
- `database_manager.py`: lớp trung gian gọi các repository.
- `tasks.py`, `users.py`, `user_tasks.py`, `daily_tasks.py`: thao tác với từng
  nhóm dữ liệu.
- `validation.py`: kiểm tra dữ liệu task và user.
- `api.py`: REST API dùng FastAPI, cung cấp các endpoint cho ứng dụng.

## 2. Cấu trúc dữ liệu

### `tasks`

Lưu lịch học, bài tập, kỳ thi, sự kiện và việc cá nhân. Các trường chính gồm:

| Trường | Mô tả |
|---|---|
| `id` | Mã task duy nhất, tối đa 64 ký tự |
| `title` | Tiêu đề, từ 2 đến 255 ký tự |
| `type` | `class`, `assignment`, `exam`, `event`, `personal` hoặc `tuition` |
| `course_code` | Mã môn theo định dạng như `CSC10004`, có thể bỏ trống |
| `registration_start`, `registration_end` | Thời gian mở/đóng đăng ký |
| `start_time`, `end_time` | Thời gian bắt đầu/kết thúc |
| `deadline` | Hạn hoàn thành |
| `estimated_hours` | Thời gian dự kiến, từ 0.25 đến 40 giờ |
| `training_points`, `drl_category` | Điểm rèn luyện và tiêu chí |
| `status` | `active`, `done`, `archived` hoặc `cancelled` |
| `is_manual` | Cho biết task do người dùng nhập |
| `source_platform` | `moodle`, `portal`, `facebook` hoặc `custom` |
| `embedding` | Dữ liệu embedding dạng văn bản |
| `updated_at` | Thời điểm cập nhật, mặc định là thời điểm hiện tại |

Các mốc thời gian phải có múi giờ, ví dụ `2026-11-01T09:30:00+07:00`.
Task loại `assignment` và `tuition` bắt buộc có `deadline`. Nếu
`training_points` lớn hơn 0 mà thiếu `drl_category`, hệ thống mặc định dùng
`dieu_3`.

### `users`

Lưu `id`, `username`, `email` và `full_name`. Username và email là duy nhất.

### `user_tasks`

Bảng liên kết user với task. Mỗi cặp `(user_id, task_id)` chỉ xuất hiện một
lần. Khi xóa user hoặc task, liên kết tương ứng được xóa theo khóa ngoại.

### `daily_tasks`

Lưu task được đưa vào lịch theo ngày và trạng thái `is_completed_today`. Mỗi
cặp `(work_date, task_id)` chỉ có một bản ghi. Khi truy vấn lịch ngày theo user,
API chỉ trả về task đã được gán cho user đó.

## 3. Cài đặt và cấu hình

Tại thư mục gốc dự án, cài dependencies:

```powershell
pip install -r requirement.txt
```

Tạo file `.env` từ `.env.example`, sau đó điền thông tin PostgreSQL:

```dotenv
DB_HOST=localhost
DB_NAME=task_manager_db
DB_USER=postgres
DB_PASSWORD=mat_khau_postgres
DB_PORT=5432
```

Không chia sẻ hoặc commit `.env` vì file này chứa thông tin xác thực.

Tạo database `task_manager_db` trong PostgreSQL nếu database chưa tồn tại.
Sau đó chạy nội dung `Db_query.sql` bằng pgAdmin hoặc `psql` để tạo các bảng và
chỉ mục. Script sử dụng `CREATE TABLE IF NOT EXISTS`, nên có thể chạy lại để
khởi tạo các bảng còn thiếu; script không tự sửa schema của bảng đã tồn tại.

## 4. Khởi chạy REST API

Chạy tại thư mục gốc dự án:

```powershell
uvicorn Database.api:app --reload
```

Mặc định API chạy tại `http://127.0.0.1:8000`. Tài liệu API tương tác của
FastAPI có tại:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

API hiện chưa có authentication. Chỉ chạy trên localhost; cần bổ sung cơ chế
xác thực và cấu hình bảo mật trước khi cho phép truy cập từ máy khác hoặc
Internet.

## 5. Các endpoint

### Tasks

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `POST` | `/tasks` | Tạo task |
| `GET` | `/tasks/{task_id}` | Lấy task theo mã |
| `PATCH` | `/tasks/{task_id}` | Cập nhật các trường được gửi lên |
| `DELETE` | `/tasks/{task_id}` | Xóa task |

Ví dụ tạo task cá nhân:

```json
{
  "id": "task-001",
  "title": "Ôn tập cơ sở dữ liệu",
  "type": "personal",
  "start_time": "2026-11-01T09:30:00+07:00",
  "end_time": "2026-11-01T11:00:00+07:00",
  "status": "active",
  "is_manual": true
}
```

Ví dụ tạo bài tập (cần có `deadline`):

```json
{
  "id": "assignment-001",
  "title": "Bài tập tuần 1",
  "type": "assignment",
  "course_code": "CSC10004",
  "deadline": "2026-11-05T23:59:00+07:00",
  "estimated_hours": 3.0
}
```

`PATCH` chỉ cần gửi các trường muốn thay đổi. Để xóa giá trị tùy chọn, gửi
trường đó với giá trị `null`. Các quy tắc kiểm tra task vẫn được áp dụng trên
toàn bộ dữ liệu sau cập nhật.

### Users và phân công task

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `POST` | `/users` | Tạo user |
| `GET` | `/users/{user_id}` | Lấy user theo ID |
| `PATCH` | `/users/{user_id}` | Cập nhật user |
| `DELETE` | `/users/{user_id}` | Xóa user |
| `GET` | `/users/{user_id}/tasks` | Xem các task đã gán |
| `PUT` | `/users/{user_id}/tasks/{task_id}` | Gán task cho user |
| `DELETE` | `/users/{user_id}/tasks/{task_id}` | Bỏ gán task |

Body tạo user:

```json
{
  "username": "sinhvien01",
  "email": "sinhvien01@example.edu",
  "full_name": "Nguyễn Văn A"
}
```

### Lịch theo ngày

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `GET` | `/users/{user_id}/daily-tasks?work_date=YYYY-MM-DD` | Xem task trong ngày của user |
| `PUT` | `/daily-tasks/{work_date}/{task_id}` | Thêm task vào ngày hoặc cập nhật trạng thái |
| `PATCH` | `/daily-tasks/{work_date}/{task_id}/completion` | Đổi trạng thái hoàn thành |
| `DELETE` | `/daily-tasks/{work_date}/{task_id}` | Xóa task khỏi ngày |

Body thêm/cập nhật task trong ngày:

```json
{
  "is_completed_today": false
}
```

Body cập nhật trạng thái hoàn thành:

```json
{
  "is_completed": true
}
```

Ngày trong đường dẫn và query dùng định dạng `YYYY-MM-DD`.

## 6. Mã trạng thái HTTP thường gặp

- `200`: thao tác đọc hoặc cập nhật thành công.
- `201`: tạo tài nguyên hoặc gán task thành công.
- `204`: xóa thành công, không có nội dung trả về.
- `404`: không tìm thấy task, user, liên kết hoặc task trong ngày.
- `409`: vi phạm ràng buộc database hoặc task đã được gán trước đó.
- `422`: request sai định dạng hoặc dữ liệu không hợp lệ.
- `500`: lỗi database ngoài các trường hợp xung đột ràng buộc.

## 7. Ghi chú sử dụng

- Mỗi thao tác database chạy trong một transaction riêng; lỗi sẽ rollback
  transaction.
- Xóa user sẽ xóa các liên kết gán task của user. Xóa task sẽ xóa liên kết
  user-task và daily-task tương ứng.
- Việc tạo task trong `daily_tasks` không tự gán task cho user. Để task xuất
  hiện trong kết quả `/users/{user_id}/daily-tasks`, trước hết hãy gán task cho
  user bằng endpoint `PUT /users/{user_id}/tasks/{task_id}`.
- Có thể dùng `DatabaseManager` trực tiếp trong Python khi không cần HTTP API;
  REST API trong tài liệu này là lớp giao tiếp dành cho ứng dụng client.
