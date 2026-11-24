# Hướng dẫn triển khai Server

Tài liệu này hướng dẫn triển khai **web client live** bằng Docker trên máy chủ
có hỗ trợ Docker. Web client dùng NiceGUI, Supabase và mã crawler chung trong
`DataProcessor`.

## 1. Kiến trúc triển khai

- `Dockerfile.web` tạo container cho giao diện web; container chạy ở chế độ
  `CLIENT_MODE=live`, bind `0.0.0.0:8080` và đặt `APP_ROLE=SERVER`.
- Task công khai được đọc từ Supabase. Nút **Run personal crawl** chỉ chạy
  Portal/Moodle cho tài khoản hiện tại; nó không chạy public crawl.
- Public crawl là workload riêng, cần triển khai Apify Actor bằng `server.py`.
  Không cần chạy Actor trong container web.
- Hướng dẫn chi tiết cho Actor nằm trong
  [PUBLIC_CRAWLER_GUIDE.md](./PUBLIC_CRAWLER_GUIDE.md).
- Web client và Actor dùng chung database nhưng nên cấu hình secrets riêng
  theo nguyên tắc tối thiểu quyền cần thiết.

## 2. Chuẩn bị Supabase

Trước khi đưa ứng dụng lên mạng:

1. Tạo/cấu hình Supabase project và các bảng theo schema trong
   `Database/Repository/`.
2. Cấu hình Supabase Auth để hỗ trợ đăng ký/đăng nhập bằng email và password.
3. Kiểm tra Row Level Security (RLS) và quyền truy cập bảng `users`, `tasks`,
   `user_task`. Client dùng public key cùng access token của người dùng; không
   dùng service-role key trong web container.
4. Nếu muốn cho phép tạo task thủ công, chạy
   `Database/Repository/custom_task_migration.sql` một lần trong Supabase SQL
   Editor. Migration này cho phép `source_platform = 'Custom'` trên
   `user_task`.
5. Đảm bảo `SUPABASE_ENCRYPTION_KEY` giống key đã dùng để mã hóa thông tin Portal
   và session Moodle hiện có. Đổi key mà không chuyển đổi dữ liệu sẽ làm dữ
   liệu đã mã hóa không giải mã được.

## 3. Cấu hình secrets

Tạo secret/environment variables trong dashboard của host hoặc secret manager.
Không đưa `.env` vào image, Git, log hoặc ticket. Các biến cho web container:

```dotenv
CLIENT_MODE=live
CLIENT_HOST=0.0.0.0
CLIENT_PORT=8080
CLIENT_STORAGE_SECRET=<random-secret-stable-between-restarts>
APP_ROLE=SERVER

SUPABASE_URL=<supabase-project-url>
SUPABASE_PUBLIC_KEY=<supabase-publishable-or-anon-key>
SUPABASE_ENCRYPTION_KEY=<existing-fernet-key>
GEMINI_API_KEY=<gemini-api-key>
```

- `CLIENT_STORAGE_SECRET` phải là chuỗi ngẫu nhiên đủ mạnh và giữ ổn định qua
  các lần restart; thay key sẽ làm các phiên browser hiện tại mất hiệu lực.
- `SUPABASE_ENCRYPTION_KEY` cần có để lưu/đọc credentials và session Portal/
  Moodle đã mã hóa.
- `GEMINI_API_KEY` cần cho bước phân tích task Moodle qua `DataProcessor`.
- `SUPABASE_SECRET_KEY`/service-role key **không cần** cho web client. Chỉ cấu
  hình quyền cao hơn ở môi trường Actor riêng khi Actor thực sự cần.
- `CLIENT_RELOAD` không nên bật trong production.

Có thể tạo storage secret bằng Python:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env.example` trong repository chỉ để tham khảo cấu trúc, không dùng nguyên
giá trị trong file làm secrets production. Nếu một secret thật từng được commit
hoặc chia sẻ, hãy đánh giá việc thu hồi/thay key; với encryption key, lên kế
hoạch chuyển đổi dữ liệu trước khi thay.

## 4. Build và chạy container

Chạy từ thư mục gốc repository sau khi đã cấu hình variables trên host:

```sh
docker build -f Dockerfile.web -t smart-calendar-web .
docker run -d --name smart-calendar-web --restart unless-stopped \
  -p 8080:8080 \
  -e CLIENT_MODE=live \
  -e CLIENT_HOST=0.0.0.0 \
  -e CLIENT_PORT=8080 \
  -e CLIENT_STORAGE_SECRET="$CLIENT_STORAGE_SECRET" \
  -e APP_ROLE=SERVER \
  -e SUPABASE_URL="$SUPABASE_URL" \
  -e SUPABASE_PUBLIC_KEY="$SUPABASE_PUBLIC_KEY" \
  -e SUPABASE_ENCRYPTION_KEY="$SUPABASE_ENCRYPTION_KEY" \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  smart-calendar-web
```

Trong production, ưu tiên nhập environment variables qua công cụ quản lý secrets
của nền tảng host thay vì lưu chúng trong shell history. Nếu host hỗ trợ
deploy từ Dockerfile, chọn `Dockerfile.web`, đặt cùng các environment
variables, và cấu hình container port `8080`.

Kiểm tra container và HTTP response:

```sh
docker ps
docker logs --tail 100 smart-calendar-web
curl -i http://127.0.0.1:8080/
```

Trang `/` phục vụ giao diện đăng nhập; HTTP 200 chỉ xác nhận web server hoạt
động, không xác nhận Supabase Auth hoặc quyền database đã đúng. Hãy thử đăng
nhập bằng tài khoản test riêng và tải Calendar trước khi mở dịch vụ cho người
dùng.

## 5. Domain, HTTPS và reverse proxy

- Dùng domain và HTTPS/TLS tại load balancer hoặc reverse proxy; không đưa
  container trực tiếp ra Internet qua HTTP không mã hóa.
- Proxy phải hỗ trợ WebSocket và giữ kết nối lâu cho NiceGUI/Socket.IO.
- Forward đúng đường dẫn, `Host`, `X-Forwarded-Proto` và WebSocket upgrade
  headers; tắt buffering cho WebSocket nếu proxy yêu cầu.
- Chỉ mở cổng công khai của reverse proxy. Hạn chế truy cập trực tiếp cổng
  `8080` từ Internet.
- Cấu hình giới hạn request, timeout đủ dài cho thao tác crawl, logging có
  kiểm soát và backup Supabase theo yêu cầu vận hành.

## 6. Giới hạn đăng nhập Portal/Moodle trên server

Container chạy `APP_ROLE=SERVER` và không thể mở browser tương tác trên máy của
người dùng:

- Nút kết nối Moodle để bắt đầu Google sign-in từ container sẽ báo cần chạy app
  trên máy cá nhân. Người dùng phải hoàn tất Moodle sign-in trong browser local
  khi app chạy `APP_ROLE=LOCAL`; session sau đó được lưu mã hóa vào Supabase.
- Mở Portal/Moodle trong tab mới chỉ mở trang chính thức để người dùng thao tác;
  browser không chia sẻ cookie/session của tab đó với crawler.
- Portal cần có credentials và session khởi tạo trước khi personal crawl chạy
  trên server. Hãy kết nối Portal trên môi trường local, hoàn tất xác minh nếu
  có, rồi để session được lưu vào database.
- Server có thể dùng session đã lưu để crawl headless. Nếu Portal/Moodle yêu
  cầu xác minh tương tác hoặc session hết hạn, người dùng có thể cần kết nối lại
  từ môi trường local.
- Không triển khai nếu yêu cầu nghiệp vụ là mọi người dùng đều tự khởi tạo hoặc
  gia hạn Google/Portal sign-in trực tiếp từ server; cần thiết kế luồng xác thực
  phù hợp trước.

## 7. Vận hành và mở rộng

- Bắt đầu với **một web replica**. Access token, lock tránh chạy crawl đồng thời
  và source preferences live hiện có trạng thái trong bộ nhớ của tiến trình.
  Nhiều replica có thể không chia sẻ các trạng thái này.
- Personal crawl chạy trong thread của web process, không phải worker độc lập.
  Restart/deploy lại giữa lúc crawl có thể làm công việc bị gián đoạn.
- Nếu cần nhiều replica hoặc crawl đáng tin cậy, cần chuyển lock/preferences
  sang storage dùng chung và đưa crawl vào hàng đợi/worker riêng.
- Thiết lập giám sát tài nguyên, lỗi container, lỗi kết nối Supabase và thời
  lượng crawl. Tránh ghi credentials, access token, cookie hoặc storage state
  vào log.
- Public crawl cần lịch chạy/trigger riêng cho Apify Actor. Kiểm tra Actor input
  và secrets của nó độc lập với web service.

## 8. Checklist trước khi mở dịch vụ

- [ ] Đã chạy migration cần thiết trên Supabase.
- [ ] RLS/Auth đã được kiểm thử bằng tài khoản người dùng thông thường.
- [ ] Tất cả secrets production được cấu hình ngoài source code và giữ ổn định.
- [ ] Image build thành công và container lắng nghe cổng `8080`.
- [ ] Domain HTTPS và WebSocket hoạt động qua reverse proxy.
- [ ] Đăng nhập, đọc Calendar, tạo task và personal crawl đã được thử với tài
      khoản test; không dùng tài khoản production để kiểm tra lỗi.
- [ ] Đã kiểm tra Portal/Moodle session bootstrap và cách xử lý khi session hết
      hạn.
- [ ] Có kế hoạch backup, xem log, restart và rollback.
- [ ] Đã quyết định cách chạy public Apify crawl và giới hạn số web replica.
