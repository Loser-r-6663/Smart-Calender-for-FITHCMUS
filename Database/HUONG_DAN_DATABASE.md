# Tài liệu cơ sở dữ liệu và hướng dẫn sử dụng

Tài liệu này mô tả cấu trúc PostgreSQL, cách cấu hình kết nối và cách sử dụng
REST API để thao tác với database của Smart Calendar.

## 1. Thành phần

- `Db_query.sql`: tạo các bảng, khóa ngoại, ràng buộc và chỉ mục.
- `db_connection.py`: đọc cấu hình từ `.env`, tạo kết nối và quản lý transaction.
- `database_manager.py`: lớp trung gian gọi các repository.
- `tasks.py`, `users.py`, `user_tasks.py`, `user_drl.py`, `daily_tasks.py`: thao tác với từng
  nhóm dữ liệu.
- `enums.py`, `task_validation.py`, `user_validation.py`: enum và kiểm tra dữ liệu.
- `task_config.py`: khai báo các trường và giá trị mặc định chung của task.
- `*_objects.py`: chuyển bản ghi từ các hàm đọc thành object có kiểu.
- `api_schemas.py`: schema cho dữ liệu cập nhật qua REST API.
- `task_schema.json`: JSON Schema mô tả payload tạo task cho client/API consumer.
- `api.py`: REST API dùng FastAPI, cung cấp các endpoint cho ứng dụng.
- `MODULES_GUIDE.md`: sơ đồ luồng và hướng dẫn nhanh các module.

## 2. Cấu trúc dữ liệu

### `tasks`

Lưu lịch học, bài tập, kỳ thi, sự kiện và việc cá nhân. Các trường chính gồm:

| Trường | Mô tả |
|---|---|
| `id` | Mã task duy nhất, tối đa 64 ký tự |
| `title` | Tiêu đề, từ 2 đến 255 ký tự |
| `type` | `class`, `assignment`, `exam`, `event`, `personal` hoặc `tuition` |
| `course` | Tên môn học, không giới hạn độ dài, có thể bỏ trống |
| `registration_start`, `registration_end` | Thời gian mở/đóng đăng ký |
| `start_time`, `end_time` | Thời gian bắt đầu/kết thúc |
| `deadline` | Hạn hoàn thành |
| `estimated_hours` | Thời gian dự kiến, từ 0.25 đến 40 giờ |
| `training_points`, `drl_category` | Điểm rèn luyện và tiêu chí |
| `status` | `active`, `done`, `archived` hoặc `cancelled` |
| `is_manual` | Cho biết task do người dùng nhập |
| `source_platform` | `moodle`, `portal`, `facebook` hoặc `custom` |
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

### `user_drl_scores`

Lưu điểm rèn luyện hiện tại theo 5 tiêu chí (`dieu_1` đến `dieu_5`) cho từng
user (`points` từ `0` đến `100`). Khi chưa có bản ghi nào cho một tiêu chí,
API trả mặc định là `0`. Khi xóa user, dữ liệu điểm rèn luyện của user đó cũng
được xóa theo khóa ngoại.

## 3. Cài đặt và cấu hình

Tại thư mục gốc dự án, cài dependencies:

```powershell
pip install -r requirements.txt
```

Tạo file `.env` từ `.env.example`, sau đó điền thông tin PostgreSQL:

```dotenv
DB_HOST=localhost
DB_NAME=task_manager_db
DB_USER=postgres
DB_PASSWORD=mat_khau_postgres
DB_PORT=5432
ADMIN_API_KEY=thay_bang_chuoi_bi_mat_dai_va_ngau_nhien
LLM_API_KEY=mot_chuoi_bi_mat_khac_danh_rieng_cho_llm
```

Không chia sẻ hoặc commit `.env` vì file này chứa thông tin xác thực.
`ADMIN_API_KEY` và `LLM_API_KEY` phải khác nhau. Tạo hai chuỗi ngẫu nhiên đủ
dài, lưu trong nơi quản lý secrets của môi trường triển khai và không gửi chúng
trong nội dung chat hoặc mã nguồn. Mỗi request API phải gửi key bằng header
`Authorization: Bearer <API_KEY>`. Không dùng nguyên các giá trị ví dụ bên dưới
làm key thực tế.

### Phân quyền API

- Logic xác thực được đặt riêng trong `Database/api_authorization.py`; các
  endpoint áp dụng dependency tương ứng trong `Database/api.py`.
- Quyền và tên biến môi trường chứa key của từng role được khai báo trong
  `Database/role_permissions.json`; key bí mật chỉ lưu trong `.env` hoặc secret
  manager, không lưu trong JSON.
- Mặc định **Admin** (`ADMIN_API_KEY`) có quyền `*` trên tất cả endpoint.
- Mặc định **LLM** (`LLM_API_KEY`) chỉ có quyền `tasks:create`, tương ứng
  endpoint `POST /tasks`. Payload được kiểm tra bởi `TaskData` trước khi API gọi
  database; dữ liệu không hợp lệ bị từ chối với HTTP 422.
- Request thiếu key hoặc key sai nhận HTTP 401; role không đủ quyền nhận HTTP
  403. Nếu file JSON không hợp lệ, key thiếu hoặc key của các role bị trùng,
  API từ chối request với HTTP 503.

Phân quyền này được áp dụng tại API; ứng dụng không được cung cấp trực tiếp
thông tin đăng nhập PostgreSQL cho LLM. Không mở API ra mạng công cộng nếu chưa
cấu hình HTTPS và biện pháp bảo vệ vận hành phù hợp.

### Hướng dẫn sử dụng phân quyền

1. Tạo các API key khác nhau, đủ dài và ngẫu nhiên. Lưu chúng vào `.env` tại
   thư mục gốc hoặc cấu hình trong secret manager của môi trường triển khai.
   Phân quyền mặc định được khai báo riêng trong
   `Database/role_permissions.json`:

   ```dotenv
   ADMIN_API_KEY=<chuoi-bi-mat-rieng-cua-admin>
   LLM_API_KEY=<chuoi-bi-mat-rieng-cua-llm>
   ```

   ```json
   {
     "roles": {
       "admin": {
         "api_key_env": "ADMIN_API_KEY",
         "permissions": ["*"]
       },
       "llm": {
         "api_key_env": "LLM_API_KEY",
         "permissions": ["tasks:create"]
       }
     }
   }
   ```

   Các quyền endpoint hiện có gồm `tasks:create/read/update/delete`,
   `users:create/read/update/delete`, `user_tasks:create/read/delete` và
   `daily_tasks:create/read/update/delete`. `*` cấp mọi quyền; role `admin`
   bắt buộc phải có `*`. Để giữ đúng nguyên tắc tối thiểu, không thêm quyền
   khác vào role `llm` nếu LLM chỉ được tạo task.

2. Khởi động API từ thư mục gốc. Sau khi thay đổi `.env` hoặc JSON, khởi động
   lại tiến trình API để nạp cấu hình mới:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn Database.api:app --reload
   ```

3. Gửi key trong header `Authorization`. Ví dụ PowerShell tạo task bằng role
   LLM (thay placeholder bằng key đã cấu hình):

   ```powershell
   $headers = @{ Authorization = "Bearer <LLM_API_KEY>" }
   $body = @{
       id = "task-llm-001"
       title = "Đọc tài liệu"
       type = "personal"
   } | ConvertTo-Json

   Invoke-RestMethod `
       -Method Post `
       -Uri "http://127.0.0.1:8000/tasks" `
       -Headers $headers `
       -ContentType "application/json" `
       -Body $body
   ```

4. Dùng `ADMIN_API_KEY` tương tự để gọi các endpoint quản trị. Ví dụ lấy task:

   ```powershell
   $headers = @{ Authorization = "Bearer <ADMIN_API_KEY>" }
   Invoke-RestMethod `
       -Method Get `
       -Uri "http://127.0.0.1:8000/tasks/task-llm-001" `
       -Headers $headers
   ```

   Admin có thể dùng các endpoint trong bảng ở mục 5. LLM chỉ được tạo task
   theo quyền mặc định; các trường thiếu, sai kiểu, sai enum hoặc không hợp lệ
   sẽ bị validation từ chối trước khi ghi database.

5. Mã HTTP khi quyền truy cập bị từ chối:

   | Mã | Ý nghĩa |
   |---|---|
   | `401` | Thiếu API key hoặc API key không đúng |
   | `403` | API key hợp lệ nhưng role không có quyền gọi endpoint |
   | `422` | Payload tạo task không vượt qua validation |
   | `503` | Chưa cấu hình đủ hai key khác nhau |

Không ghi key vào log, mã nguồn, Git hoặc gửi key LLM cho người dùng. Khi key
bị lộ, thay key trong cấu hình bảo mật và khởi động lại API.

Tạo database `task_manager_db` trong PostgreSQL nếu database chưa tồn tại.
Sau đó chạy nội dung `Db_query.sql` bằng pgAdmin hoặc `psql` để tạo các bảng và
chỉ mục. Script cũng chuyển `course`, `target_audience`, `location`, `email` và
`full_name` sang kiểu `TEXT` để bỏ giới hạn 100 ký tự của schema cũ; cột
`username` vẫn giới hạn 50 ký tự. Script xóa các cột `course_code`, `embedding`
của schema cũ, vì vậy hãy sao lưu database trước khi chạy lại.

## 4. Khởi chạy REST API

Chạy tại thư mục gốc dự án:

```powershell
uvicorn Database.api:app --reload
```

Mặc định API chạy tại `http://127.0.0.1:8000`. Tài liệu API tương tác của
FastAPI có tại:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Tất cả endpoint dữ liệu yêu cầu API key theo phần phân quyền ở trên. Chỉ chạy
trên localhost; cần cấu hình HTTPS và bảo vệ phù hợp trước khi cho phép truy cập
từ máy khác hoặc Internet.

## 5. Các endpoint

### Tasks

Payload tạo task được mô tả trong `Database/task_schema.json`; API dùng
`TaskData` trong `Database/task_validation.py` để thực thi validation.

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `POST` | `/tasks` | Tạo task |
| `GET` | `/tasks` | Lấy danh sách task (hỗ trợ lọc tùy chọn `?status=...&type=...`) |
| `GET` | `/tasks/{task_id}` | Lấy task theo mã |
| `PATCH` | `/tasks/{task_id}` | Cập nhật các trường được gửi lên |
| `DELETE` | `/tasks/{task_id}` | Xóa task |

Query params tùy chọn của `GET /tasks`:
- `status`: `active`, `done`, `archived` hoặc `cancelled`.
- `type`: `class`, `assignment`, `exam`, `event`, `personal` hoặc `tuition`.

Kết quả được sắp xếp theo `start_time` tăng dần (null ở cuối), `deadline` tăng dần (null ở cuối), rồi đến `id`. Endpoint yêu cầu quyền `tasks:read`.

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
  "course": "Cơ sở dữ liệu",
  "deadline": "2026-11-05T23:59:00+07:00",
  "estimated_hours": 3.0
}
```

`PATCH` chỉ cần gửi các trường muốn thay đổi. Để xóa giá trị tùy chọn, gửi
trường đó với giá trị `null`. Các quy tắc kiểm tra task vẫn được áp dụng trên
toàn bộ dữ liệu sau cập nhật.

Trước khi ghi database, task được kiểm tra kiểu, độ dài và định dạng của từng
trường; các mốc thời gian phải có múi giờ, `source_url` phải là URL HTTP(S),
và `recurrence` phải theo dạng `T2 08:00-10:00` (một ngày và khoảng giờ 24
tiếng; ngày hợp lệ là `T2`–`T7` hoặc `CN`). Thời gian bắt đầu phải trước thời
gian kết thúc. Các trường không khai báo bị từ chối.
Task đọc qua `DatabaseManager` được trả về dưới dạng object trong
`Database.objects`.

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
| `GET` | `/users/{user_id}/drl` | Xem điểm ĐRL hiện tại 5 Điều của user |
| `PUT` | `/users/{user_id}/drl` | Đặt lại toàn bộ điểm ĐRL 5 Điều (mặc định 0) |
| `PATCH` | `/users/{user_id}/drl` | Cập nhật từng mục điểm ĐRL được gửi lên |

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
