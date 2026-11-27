> The integrated app uses the loaded, scoped Search controls and read-only detail dialog described in README.md. Section 7 gives a reproducible Vietnamese Search demo alongside the FE task-management and scheduling flows.

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

## 7. Demo Search trên bản tích hợp

Bản kiểm tra: `FE-Client` tại `5ad961d44437b5d1681d280a777397b977d0a0a1`
(FE `67fea68` + Search/P `2a4fe34`). Kết quả chi tiết và các kiểm tra chưa
thực hiện nằm trong [biên bản demo](fixtures/search_demo/VERIFICATION.md).
Phần này không yêu cầu crawl, Auto-schedule hay thay đổi dữ liệu thật.

### Chuẩn bị dữ liệu giả lập cố định

Từ thư mục gốc, dùng Python của dự án thay vì Python hệ thống thiếu dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mockweb.txt
$env:PYTHON_DOTENV_DISABLED = '1'
Remove-Item Env:SEARCH_SEMANTIC_MODEL -ErrorAction SilentlyContinue
$env:CLIENT_PORT = '8091'
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_demo.app
```

Mở cửa sổ riêng tư tại `http://127.0.0.1:8091/login`, đăng nhập `student` /
`demo`. Đây là **mock**, gồm 15 bản ghi hư cấu trong
`fixtures/search_demo/tasks.json`, không phải hai bản export. Giữ tất cả
Information sources bật. Search và Calendar dùng cùng snapshot; bộ lọc và
lựa chọn của hai phần độc lập. Không bấm crawl, tạo task hay lập lịch trong demo.

1. **Tìm chính xác và mở nguồn.** Mở **Search tasks**; lúc đầu chưa có kết quả.
   Nhập `Thời điểm hoàn tất nghĩa vụ tài chính`, nhấn Enter. Có một kết quả,
   key `public:11111111-1111-4111-8111-111111111111`. Chọn kết quả: dialog
   hiện tiêu đề, deadline gốc và **Open official source**. Liên kết ở launcher
   này dẫn tới trang nguồn giả lập trên cùng máy, không tới tài khoản thật.
   Close/Escape đóng dialog và trả focus về kết quả. Đóng/mở popover giữ lại
   Search; Clear trả Search về idle và không đổi lịch.
2. **So sánh điểm.** Clear rồi lần lượt submit `5 điểm`, `từ 5 điểm`,
   `nhiều hơn 5 điểm`. Kết quả tương ứng là **1 / 2 / 1 task**: cá nhân
   `88888888-8888-4888-8888-888888888888` (5 điểm); thêm công khai
   `66666666-6666-4666-8666-666666666666` (7 điểm); cuối cùng chỉ task 7 điểm.
   Task 4, 0 và thiếu điểm không lọt vào các kết quả này. `bé hơn 5 điểm`
   lấy task 4 và 0 điểm. Đây là so sánh task sự kiện, không phải scope riêng tư.
   Giao diện chỉ hiện số task và thứ tự; không có nhãn tóm tắt điểm suy luận.
3. **Bài tập trong một tuần.** Clear, để ô Search trống; chọn Type
   **Assignments**, Course **CSC10006**, Deadline from **2026-11-30** và
   Deadline through **2026-12-06**; nhấn Search. Hai đầu ngày đều được tính
   theo giờ Việt Nam. Ba task hư cấu là:

   | Ký hiệu | Tiêu đề | Deadline Việt Nam | Key (scope luôn là `personal`) |
   | --- | --- | --- | --- |
   | C | Chuẩn bị truy vấn dữ liệu | 30/11 00:00 | `a7100000-0000-4000-8000-000000000001` |
   | B | Báo cáo thực hành cơ sở dữ liệu | 04/12 09:00 | `33333333-3333-4333-8333-333333333333` |
   | G | Ghi chú thiết kế bảng | 06/12 23:59 | `a7100000-0000-4000-8000-000000000002` |

   **Soonest deadline:** C → B → G; **Latest deadline:** G → B → C;
   **Title A–Z:** B → C → G. Mỗi lần vẫn cùng ba key. Sửa ngày bắt đầu thành
   07/12 để thấy lỗi khoảng đảo, rồi sửa lại mà không nhập lại query.
   Calendar/Agenda/Schedule và bộ lọc loại ở toolbar vẫn hoạt động riêng.

### Demo diễn đạt khác nghĩa đen (model tùy chọn, chạy trên máy)

Dừng launcher bằng Ctrl+C. Cài model một lần; revision cố định, license MIT,
CPU, khoảng 488 MB assets, không nằm trong Git:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.setup_model "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_demo.app
```

Model `intfloat/multilingual-e5-small`, revision
`fd1525a9fd15316a2d503bf26ab031a61d056e98`, cutoff **0.86**.
Mở lại phiên riêng tư, Clear các bộ lọc, tìm `hạn cuối đóng học phí`.
Task **Thời điểm hoàn tất nghĩa vụ tài chính** là đích mong đợi, rank 1 trên
fixture demo đã kiểm tra; keyword-only không tìm thấy. Query không có từ
literal nào trong title/description của task này. Chọn nó để mở cùng dialog
và nguồn giả lập. Lần đầu có thể hiện **Searching…** trong khi chuẩn bị;
kết quả ban đầu vẫn dùng được, số lượng cuối chỉ hiện sau khi hoàn tất.
Chuẩn bị chạy nền, không chặn lịch; với nhiều task, chờ model có thể lâu.

Không có model: bỏ `SEARCH_SEMANTIC_MODEL` như lệnh đầu rồi khởi động lại.
Exact, điểm, course, ngày và sort vẫn dùng được; paraphrase trên không có hit.
Không có truy vấn/task nào được gửi tới dịch vụ embedding bên ngoài.

Kiểm tra lại trên tập E **14 task / 31 case** (khác fixture demo 15 task):

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.check_prepared --output fixtures/search_semantic/hybrid_integrated_report.json
```

Đây là regression trên các case đã xem: keyword **1/3 tuning, 0/4 held-out**;
model **3/3 tuning, 1/4 held-out**; cả hai **0/4 unrelated false hits**, không
có vi phạm correctness. Không diễn giải thành khả năng hiểu mọi câu tiếng Việt.

### Đối chiếu live chỉ đọc

Dùng cấu hình public-client và hướng dẫn live ở mục 2, không dùng service-role
key. Không để `PYTHON_DOTENV_DISABLED=1` nếu cần đọc `.env`; nhập mật khẩu qua
trang đăng nhập, không ghi vào lệnh, ảnh hay biên bản. Với nguồn bật giống nhau,
có thể dùng tiêu đề công khai **Tổng kết Buổi giới thiệu về các chương trình
học bổng trường Đại học Quốc gia Seoul (Hàn Quốc)** để exact lookup. Public key
`public:322661b8-b705-4723-a512-04b426028960` được kiểm tra qua repository guest,
rank 1, trong 23 hàng live ngày 27/11/2026; không phải kiểm tra guest qua Calendar.
Nguồn công khai nằm trong dialog; chưa kiểm tra đích Facebook bằng tài khoản thật.

Search chỉ bao phủ originals được cấp quyền và nguồn đang bật, gồm cả task
không ngày/chưa xếp lịch; dialog giữ facts gốc, khác overlay xếp lịch Calendar.
Không dùng export cá nhân để suy ra quyền: phải xác thực A/B, đọc đúng owner,
thử private key với owner, account kia và guest, rồi chuyển account khi dialog
đang mở. Kiểm tra live ngày 27/11/2026: guest/A/B cùng thấy **23 public task**;
A có **12 private task**, tìm và mở đúng original/source; B và guest không tìm
hoặc resolve được private key đó. Logout khi dialog của A đang mở xóa details,
link và lựa chọn; callback cũ bị từ chối. Query/details không đọc task thêm.
B có **0 private task**, khớp export theo identity đã xác thực; chưa có fixture
để thử chiều B → A/guest, không tạo dữ liệu thật để bù. Kết quả ẩn danh trong
`fixtures/search_demo/live_accounts_verification.json`; không ghi credentials,
private title/key/URL hoặc ảnh riêng tư. Phản hồi paraphrase mới từ đồng đội,
review layout của Long và xác nhận shared build của Hiển: **đang chờ**.
