# Hướng dẫn nhanh các module Database

Tài liệu này giới thiệu các file triển khai trong thư mục `Database`. Các file
test và công cụ test thủ công không nằm trong danh sách.

## Luồng xử lý chính

```text
HTTP request
  -> api.py
  -> api_authorization.py (đọc role_permissions.json, API key và quyền)
  -> api_schemas.py / task_validation.py / user_validation.py
  -> database_manager.py
  -> tasks.py / users.py / user_tasks.py / daily_tasks.py
  -> db_connection.py
  -> PostgreSQL (Db_query.sql)
```

Kết quả truy vấn được chuyển thành object trong các module `*_objects.py` trước
khi trả về từ `DatabaseManager`.

## Danh sách file

### API và điều phối

| File | Vai trò |
|---|---|
| `api.py` | Khai báo FastAPI, endpoint, dependency database và ánh xạ lỗi HTTP. |
| `api_authorization.py` | Đọc `role_permissions.json`, xác thực Bearer API key và kiểm tra quyền endpoint. |
| `role_permissions.json` | Khai báo tên biến chứa API key và quyền cho từng role; không lưu key bí mật trong file này. |
| `api_schemas.py` | Schema request khi cập nhật task, user và trạng thái task theo ngày. |
| `database_manager.py` | Điều phối repository, transaction và chuyển bản ghi đọc thành object. Đây là DatabaseManager dùng bởi API. |
| `DatabaseManager.py` | DatabaseManager kiểu kết nối trực tiếp cũ; được giữ để tương thích với luồng gọi cũ. Với code mới, ưu tiên `database_manager.py`. |

### Repository

| File | Vai trò |
|---|---|
| `tasks.py` | Tạo, đọc, cập nhật và xóa task; xác thực task trước khi ghi. |
| `users.py` | Tạo, đọc, cập nhật và xóa user. |
| `user_tasks.py` | Gán/bỏ gán task và truy vấn các liên kết user-task. |
| `daily_tasks.py` | Thêm task vào ngày, truy vấn lịch ngày và cập nhật trạng thái hoàn thành. |

### Schema, cấu hình và xác thực

| File | Vai trò |
|---|---|
| `enums.py` | Enum dùng chung cho loại task, trạng thái, tiêu chí ĐRL và nền tảng nguồn. |
| `task_config.py` | Tập trung các trường task, giá trị mặc định và hàm tạo timestamp hiện tại. |
| `task_validation.py` | Model task và quy tắc kiểm tra định dạng, miền giá trị, thời gian và quan hệ trường. |
| `user_validation.py` | Model user và kiểm tra dữ liệu user. |
| `validation.py` | Module tương thích, tái xuất các model/helper từ module xác thực chuyên biệt. Nên dùng module chuyên biệt khi viết code mới. |

### Object kết quả truy vấn

| File | Vai trò |
|---|---|
| `task_objects.py` | Chuyển bản ghi task thành `TaskObject`. |
| `daily_task_objects.py` | Object task theo ngày, mở rộng task với ngày và trạng thái hoàn thành. |
| `user_objects.py` | Object user và liên kết user-task. |
| `objects.py` | Module tương thích, tái xuất các object từ file chuyên biệt. |

### Database và tài liệu

| File | Vai trò |
|---|---|
| `db_connection.py` | Tạo kết nối PostgreSQL từ `.env` và quản lý transaction. |
| `db_config.py` | Đọc cấu hình môi trường theo helper cũ; được `DatabaseManager.py` sử dụng. |
| `Db_query.sql` | Tạo bảng, ràng buộc, index và migration schema task hiện tại. |
| `HUONG_DAN_DATABASE.md` | Hướng dẫn cài đặt database và sử dụng REST API. |
| `MODULES_GUIDE.md` | Tài liệu tham khảo nhanh về vai trò và luồng của các module. |

## Cách sử dụng nhanh

### Chạy REST API

Từ thư mục gốc dự án:

```powershell
uvicorn Database.api:app --reload
```

### Dùng DatabaseManager trong Python

```python
from Database.database_manager import DatabaseManager

database = DatabaseManager()
task = database.get_task("task-001")
```

`get_task`, `get_user`, `get_user_tasks` và `get_tasks_by_date` trả về object
được định nghĩa trong các module `*_objects.py`. Dùng `model_dump()` để đổi
object Pydantic thành dictionary.

### Thêm quy tắc hoặc trường task

1. Khai báo giá trị mặc định ở `task_config.py` nếu trường cần mặc định chung.
2. Thêm kiểu và quy tắc xác thực vào `task_validation.py`; enum dùng chung đặt
   trong `enums.py`.
3. Cập nhật danh sách cột cho phép trong cấu hình task, cùng schema/migration ở
   `Db_query.sql`.
4. Cập nhật `api_schemas.py` nếu trường được phép gửi qua API `PATCH`.
5. Cập nhật object hoặc repository tương ứng nếu cấu trúc kết quả/truy vấn đổi.
6. Cập nhật `HUONG_DAN_DATABASE.md` nếu cách dùng API/schema thay đổi.

`validation.py` và `objects.py` chỉ giữ vai trò tương thích; tránh thêm logic
mới vào hai file này.

## Chạy test database

Test repository/mock không cần PostgreSQL:

```powershell
python -m unittest discover -s tests -v
```

Test tích hợp tạo và xóa user/task thử trên PostgreSQL đã cấu hình trong `.env`:

```powershell
$env:RUN_POSTGRES_INTEGRATION = "1"
python -m unittest discover -s tests -p "test_postgres_integration.py" -v
```

Chỉ bật test tích hợp khi `.env` trỏ đến database dành cho test. Test yêu cầu
schema trong `Db_query.sql` đã được áp dụng và sẽ tạo/xóa dữ liệu thử.
