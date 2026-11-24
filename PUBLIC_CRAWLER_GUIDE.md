# Hướng dẫn chạy riêng Public Crawler

Public crawler thu thập thông báo từ các website/trang công khai, phân tích task
bằng Gemini và lưu vào bảng `tasks` trên Supabase. Đây là workload riêng, không
được khởi chạy bởi web client.

## 1. Nguồn dữ liệu

`DataProcessor.TaskCreator` định nghĩa các nguồn public gồm website FIT, HCMUS,
Phòng Công tác sinh viên và các trang Facebook của trường/khoa. Mỗi nguồn có
thể gặp lỗi riêng; lỗi crawl một nguồn được ghi log và các nguồn sau vẫn được
thử.

Crawler dùng link bài viết cuối đã xử lý để tránh crawl lại các bài cũ. Trên
Apify, các mốc này được giữ trong Key-Value Store tên `History`.

## 2. Chạy bằng Apify (khuyến nghị)

Apify Actor dùng `Dockerfile` và `server.py` tại thư mục gốc. Cần cài Apify CLI
và đăng nhập CLI vào tài khoản Apify:

```sh
npm install -g apify-cli
apify login
```

Từ thư mục gốc repository, đẩy Actor:

```sh
apify push
```

### Cấu hình Actor

Trong Apify Console, mở Actor **HCMUS Assistant Crawler** và kiểm tra các
environment variables/secrets được cấu hình:

| Biến | Mục đích |
| --- | --- |
| `APP_ROLE` | Đặt chính xác `SERVER` để dùng Apify Key-Value Store và chế độ headless. |
| `SUPABASE_SECRET_KEY` | Quyền ghi/đọc các task public trong bảng `tasks`; giữ secret, không dùng public key. |
| `SUPABASE_URL` | URL project Supabase. |
| `GEMINI_API_KEY` | Phân tích nội dung bài viết thành task có cấu trúc. |
| `SUPABASE_ENCRYPTION_KEY` | Có trong cấu hình Actor chung; public crawl không xử lý user credentials nhưng giá trị phải khớp nếu Actor cũng được dùng cho personal crawl. |

`.actor/actor.json` ánh xạ biến môi trường `SUPABASE_SECRET_KEY` tới secret
Apify tên `SUPABASE_KEY`. Hãy tạo/cập nhật secret đó trong Apify Console. Không
đưa service key vào `SUPABASE_PUBLIC_KEY`, Git, file input hay log.

### Chỉ chạy public mode

Khi chạy Actor, đặt input:

```json
{
  "mode": "public"
}
```

Mặc định `server.py` cũng chọn `public` nếu Actor input không có `mode`; vẫn nên
đặt rõ `"public"` để tránh vô tình chạy personal crawl khi entrypoint được đổi.
Không chọn `"all"` hoặc `"personal"` nếu mục tiêu chỉ là public sources.

Nhấn **Start** trong Actor Console và theo dõi log của run. Log cho biết nguồn
nào đang crawl, số bài được phân tích và số task mới được lưu/xóa. Task đã có
trong Supabase được deduplicate; crawl lại không đồng nghĩa luôn có task mới.

### Lên lịch

Sau khi chạy thử thành công, tạo Schedule trong Apify Console để chạy Actor
định kỳ. Gắn input `{"mode":"public"}`, chọn múi giờ phù hợp (thường là
`Asia/Ho_Chi_Minh`) và tránh tạo các schedule chạy chồng lấn. Tần suất nên phù
hợp với giới hạn nguồn và ngân sách Gemini/Apify.

## 3. Chạy local có kiểm soát

Local run có thể gọi tới các website bên ngoài, dùng Gemini API và **ghi/xóa dữ
liệu thật trên Supabase**. Không có chế độ dry-run trong `server.py`; chỉ thử
với staging database/keys nếu không muốn tác động dữ liệu production.

Trong PowerShell, từ thư mục gốc repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:APP_ROLE = "LOCAL"
$env:SUPABASE_URL = "<staging-supabase-url>"
$env:SUPABASE_SECRET_KEY = "<staging-secret-key>"
$env:GEMINI_API_KEY = "<gemini-api-key>"
python server.py
```

`server.py` chạy `main(mode="public")` khi được gọi trực tiếp. Ở local,
crawler lưu history vào `DataProcessor/Crawler/History/` thay vì Apify
Key-Value Store. Giữ thư mục này nếu muốn lần chạy sau tiếp tục từ bài mới;
xóa history sẽ khiến crawler quét lại các bài cũ và tăng số request/API calls.

Không đặt `APP_ROLE=SERVER` khi chạy trực tiếp ngoài Actor: ở chế độ này,
crawler cần Apify Actor context và Apify Key-Value Store.

## 4. Facebook sources

Các crawler Facebook chạy headless trên Actor chỉ khi có browser state hợp lệ
trong Apify Key-Value Store tên `State`, key `FBState`. Nếu state chưa có/hết
hạn, các nguồn Facebook có thể bị bỏ qua; các nguồn website khác vẫn có thể
chạy. `FB_USERNAME`/`FB_PASSWORD` không thay thế state này trong chế độ
`SERVER`, và không nên dùng credentials cá nhân Facebook để né xác thực hoặc
giới hạn của nền tảng.

## 5. Kiểm tra dữ liệu và xử lý lỗi

- Xác nhận Supabase có task mới trong bảng `tasks`, với `source_platform` đúng
  và link nguồn có thể mở.
- Kiểm tra Actor log theo từng nguồn. Crawl một nguồn lỗi không nhất thiết làm
  toàn bộ Actor run thất bại.
- Nếu không lưu được task, kiểm tra `SUPABASE_URL`, secret `SUPABASE_KEY` được
  ánh xạ vào `SUPABASE_SECRET_KEY`, và quyền database của key.
- Nếu không có task mới, có thể các bài đã được crawl trước đó, parser không
  trích xuất được task, hoặc website thay đổi cấu trúc.
- Nếu gặp lỗi Gemini, kiểm tra key, quota, quyền model và log lỗi API.
- Actor cần quyền ghi lên Apify Key-Value Store để đọc/ghi lịch sử `History`.
- Không ghi Supabase service key, Gemini key, cookies hoặc browser state vào
  log hay dữ liệu Actor công khai.

## 6. Phạm vi không thuộc public crawler

- Portal và Moodle là personal sources; chúng được chạy riêng theo người dùng
  qua web client/`DataProcessor`, không thuộc mode `public`.
- Public crawler không mở giao diện lịch và không phục vụ HTTP request.
- `Dockerfile.web` dành cho web client; public crawler dùng `Dockerfile` và
  Apify Actor.
