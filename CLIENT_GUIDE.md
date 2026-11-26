> The integrated app uses the loaded, scoped Search controls and read-only detail dialog described in README.md. This guide covers the FE task-management and scheduling flows.

# Hướng dẫn sử dụng Client

Tài liệu này hướng dẫn cài đặt và chạy giao diện NiceGUI trong thư mục `client/`.
Client dùng `DataProcessor` cho personal crawl; không dùng package `Backend`.
Để triển khai container lên server, xem [SERVER_GUIDE.md](./SERVER_GUIDE.md).

## 1. Client làm gì?

- Hiển thị task công khai và task cá nhân trên lịch tháng hoặc danh sách Agenda.
- Lọc theo loại task, tìm kiếm, xem chi tiết và mở nguồn chính thức.
- Kết nối tài khoản Student Portal và Moodle để lấy thời khóa biểu, hạn nộp bài.
- Chạy personal crawl theo yêu cầu và lưu task cá nhân vào database.

Client có hai chế độ:

| Chế độ | Backend dữ liệu | Dùng khi |
| --- | --- | --- |
| `mock` | Fixture cục bộ tại `client/fixtures/tasks.json` | Phát triển giao diện, không cần Supabase |
| `live` | Supabase qua các repository trong `Database/` | Dùng tài khoản và dữ liệu thật |

## 2. Cài đặt môi trường

Yêu cầu Python 3.12 và PowerShell trên Windows. Chạy các lệnh từ thư mục gốc
repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn kích hoạt môi trường ảo, có thể gọi Python trực tiếp qua
`.\.venv\Scripts\python.exe`.

### Chỉ chạy mock

```powershell
python -m pip install -r requirements-mockweb.txt
$env:CLIENT_MODE = "mock"
python -m client.main
```

Đăng nhập demo:

- Tên đăng nhập: `student`
- Mật khẩu: `demo`

Mock dùng dữ liệu fixture; đăng nhập, kết nối Portal/Moodle và crawl đều là mô
phỏng, không truy cập tài khoản hoặc database thật.

### Chạy live

Cài dependencies của client và `DataProcessor`:

```powershell
python -m pip install -r requirements.txt -r requirements-web.txt
```

Tạo file `.env` tại thư mục gốc và cấu hình các biến cần thiết:

```dotenv
CLIENT_MODE=live
CLIENT_HOST=127.0.0.1
CLIENT_PORT=8080
CLIENT_STORAGE_SECRET=<chuỗi-ngẫu-nhiên-dài-và-ổn-định>
APP_ROLE=LOCAL

SUPABASE_URL=<URL-project>
SUPABASE_PUBLIC_KEY=<public-key>
SUPABASE_ENCRYPTION_KEY=<Fernet-key>
GEMINI_API_KEY=<Gemini-key>
```

Các giá trị phải lấy từ cấu hình được cấp cho project; không đưa key thật vào
tài liệu, mã nguồn, ảnh chụp hoặc Git. `.env` đã được Git ignore. Có thể tạo
storage secret bằng:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Giữ nguyên `CLIENT_STORAGE_SECRET` giữa các lần khởi động để phiên đăng nhập
trình duyệt không bị mất. Nếu thay secret, người dùng cần đăng nhập lại.
`SUPABASE_ENCRYPTION_KEY` được dùng để mã hóa/giải mã thông tin Portal và
session Moodle đã lưu; không đổi key nếu chưa có kế hoạch chuyển đổi dữ liệu
đang mã hóa.

Trước khi dùng chức năng tạo task ở live, chạy migration
[`custom_task_migration.sql`](./Database/Repository/custom_task_migration.sql)
trong SQL Editor của Supabase để cho phép nguồn `Custom` trong `user_task`.

Khởi động client live:

```powershell
$env:CLIENT_MODE = "live"
$env:APP_ROLE = "LOCAL"
python -m client.main
```

Mở <http://127.0.0.1:8080>. Có thể thay `CLIENT_HOST` hoặc `CLIENT_PORT` nếu
cần địa chỉ/cổng khác. Nếu cổng đang được dùng, đổi `CLIENT_PORT` hoặc dừng
ứng dụng đang chiếm cổng đó.

## 3. Luồng sử dụng live

1. Tạo tài khoản bằng email và mật khẩu hoặc đăng nhập tài khoản hiện có.
2. Mở **Settings**:
   - **Student Portal**: nhập mã sinh viên và mật khẩu Portal. Sau khi lưu, chạy
     personal crawl để đăng nhập và lấy session. Nếu Portal yêu cầu xác minh,
     hoàn tất bước đó trong cửa sổ trình duyệt được mở. Có thể mở Portal bằng
     liên kết trong dialog để kiểm tra tài khoản; đăng nhập ở tab mới không
     chuyển session sang crawler.
   - **Moodle**: có thể mở Moodle trong tab mới, nhưng để lưu session cho
     crawler, chọn **Capture Moodle session** và hoàn tất Google sign-in trong
     cửa sổ trình duyệt riêng được mở. Không nhập mật khẩu Google vào Smart
     Calendar.
3. Bật các nguồn muốn sử dụng trong **Information sources**.
4. Chọn **Run personal crawl** ở Calendar hoặc Settings để lấy dữ liệu Portal
   và/hoặc Moodle đã kết nối.
5. Quay lại Calendar. Chuyển tháng, lọc Classes/Assignments/Events/Notices,
   tìm task, đổi giữa Calendar và Agenda; chọn task để xem mô tả và liên kết
   nguồn.
6. Chọn **New task** để mở form tạo task cá nhân. Nhập tiêu đề và loại task;
   ngày, giờ, deadline, môn học, địa điểm, mô tả và liên kết nguồn là tùy chọn.
   Task có ngày sẽ được lưu vào lịch cá nhân; task không có ngày sẽ hiển thị
   trong Agenda. Chọn task tự tạo để sửa hoặc xóa; task từ nguồn crawler không
   có các thao tác này. Ở live, thay đổi chỉ áp dụng cho task `Custom` thuộc
   tài khoản hiện tại trong `user_task`. Ở mock, task chỉ tồn tại trong bộ nhớ
   của phiên chạy.

Thông tin Portal và session Moodle được lưu mã hóa ở database. Tài khoản
Smart Calendar dùng Supabase Auth; đổi mật khẩu trong Settings sẽ đăng xuất
phiên hiện tại.

## 4. Dữ liệu và cách chạy crawler

- Client đọc task công khai từ bảng `tasks`, và task cá nhân của người dùng từ
  `user_task`. Các truy vấn được phân trang để không bỏ sót dữ liệu sau trang
  đầu.
- Personal crawl gọi chung mã crawler từ `DataProcessor`, sau đó lưu task cá
  nhân vào `user_task`.
- Personal crawl chạy trong một thread của tiến trình web client; đây không
  phải worker riêng. Nếu dừng client trong lúc crawl, tiến trình crawl cũng
  dừng.
- Crawl nguồn công khai do Apify Actor riêng đảm nhiệm. Nút **Run personal
  crawl** trong client không khởi chạy public crawl.
- Xem [PUBLIC_CRAWLER_GUIDE.md](./PUBLIC_CRAWLER_GUIDE.md) để chạy và lên lịch
  public crawler.
- Thiết lập bật/tắt nguồn trong live hiện được giữ trong bộ nhớ của tiến trình;
  chúng có thể trở về mặc định sau khi restart client.
- Moodle Google sign-in cần trình duyệt tương tác trên chính máy chạy client.
  Cài browser của Playwright nếu máy chưa có:

  ```powershell
  python -m playwright install chromium
  ```

  Không dùng cấu hình `APP_ROLE=SERVER` để thực hiện lần đăng nhập tương tác
  Portal/Moodle. Cấu hình container trong `Dockerfile.web` chạy ở chế độ
  `SERVER`; phù hợp hơn cho triển khai headless sau khi đã có session hợp lệ.

## 5. Kiểm thử

Chạy toàn bộ test:

```powershell
python -m pytest -q
```

Các test client và database repository nằm trong thư mục `tests/`.

## 6. Xử lý sự cố thường gặp

| Hiện tượng | Kiểm tra |
| --- | --- |
| Không mở được trang | Kiểm tra client còn chạy, đúng `CLIENT_HOST`/`CLIENT_PORT`, và cổng chưa bị tiến trình khác chiếm. |
| Đăng nhập live thất bại hoặc báo dịch vụ không khả dụng | Kiểm tra `CLIENT_MODE=live`, Supabase URL/public key, kết nối mạng, cấu hình Supabase Auth và quyền truy cập các bảng. |
| Không thấy task cá nhân | Kết nối Portal/Moodle, bật nguồn tương ứng trong Settings rồi chạy **Run personal crawl**. |
| Không thấy task công khai | Kiểm tra đã có dữ liệu trong bảng `tasks`; public crawl chạy riêng trên Apify, không chạy từ client. |
| Moodle không kết nối được | Chạy client trên máy có trình duyệt, đặt `APP_ROLE=LOCAL`, cài Chromium bằng Playwright và hoàn tất Google sign-in trong cửa sổ được mở. |
| Portal không lấy được dữ liệu | Kiểm tra mã sinh viên/mật khẩu, hoàn tất xác minh nếu được yêu cầu, rồi chạy crawl lại. |
| Task hiển thị “No date” | Kiểm tra dữ liệu thời gian của task trong database và log lỗi khi tải task; task không có ngày/giờ có thể được xếp vào nhóm thông báo không ngày. |
| Sau khi restart bị yêu cầu đăng nhập lại | Kiểm tra `CLIENT_STORAGE_SECRET` có bị đổi không. Dùng cùng secret để giữ phiên trình duyệt. |
