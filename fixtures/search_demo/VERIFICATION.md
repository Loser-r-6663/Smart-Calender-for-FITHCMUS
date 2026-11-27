# Biên bản Search trên FE tích hợp — 27/11/2026

Build được kiểm tra: **`5ad961d44437b5d1681d280a777397b977d0a0a1`**, branch
`FE-Client`, parents `67fea68428dd685fddb381a40235b89e16e398d1` và
`2a4fe342a73306c1739cde8ad01a7065d868e11e`. Đây là SHA build, chưa phải SHA
Commit 7. Công việc mới chưa commit; không đổi runtime Search/client, ranking,
threshold, policy hay schema. Hướng dẫn thao tác nằm trong mục 7 của
[CLIENT_GUIDE.md](../../CLIENT_GUIDE.md).

## Môi trường và dữ liệu

- Windows, Intel Core i5-8265U @ 1.60 GHz, CPU ONNX dùng 2 threads.
- `.\.venv\Scripts\python.exe`: Python 3.12.14; pytest 9.2.0 (subtests tích hợp),
  NiceGUI 3.19.0, Playwright 1.65.2, Requests 2.34.2, Pydantic 2.14.4,
  ONNX Runtime 1.23.2, Tokenizers 0.22.1, NumPy 2.5.5. Edge **158.0.4370.33**,
  phiên bản cũng ghi trong `ui_verification.json`.
- Model tùy chọn `intfloat/multilingual-e5-small`, MIT, revision
  `fd1525a9fd15316a2d503bf26ab031a61d056e98`, cutoff **0.86**. Weights,
  tokenizer và model card: **487,848,778 bytes**, cộng file revision 42 bytes;
  lưu ngoài Git. Setup giữ nguyên theo [HYBRID.md](../search_semantic/HYBRID.md).
- Tập E đóng băng vẫn là 14 task / 31 case. `tasks.json` ở thư mục này là
  **fixture demo riêng**, 13 bản ghi public/account-A được chiếu vào mock
  `demo-user`, thêm hai assignment hư cấu để thấy cả hai đầu tuần và ba thứ tự.
  Không sửa corpus, judgments, split, manifest hay keyword report của E.
- Không có task thật, password, token, private URL hoặc raw export trong
  fixture, ảnh hay báo cáo. Hai export ngoài repo chỉ được đọc như JSON.

## Quan sát live trực tiếp (chỉ đọc)

`live_public_verification.json` ghi guest qua **`load_snapshot()` / repository**,
không phải guest trên trang Calendar vốn yêu cầu đăng nhập. Chỉ dùng public
client key, chặn mọi HTTP method ngoài GET, không sử dụng service-role key.

- Live **23 public rows**, trùng 23 UUID public trong export; không có row
  thiếu/thừa. All sources enabled; một GET `tasks`, public scope, không cap.
- Exact public lookup `public:322661b8-b705-4723-a512-04b426028960` rank **1**;
  details lấy từ snapshot, đúng URL nguồn công khai. Các query `5 điểm`,
  `từ 5 điểm`, `nhiều hơn 5 điểm` trả **3 / 6 / 3** public task, khớp kỳ vọng
  độc lập từ public export. Search/detail phát sinh **0 request bổ sung**.
- Personal export có 46 row / 5 owners; số lượng này **không chứng minh quyền**.
  Cả năm nhóm có ứng viên title để thử exact lookup, chỉ một nhóm có title
  riêng không trùng public/owner khác; không ghi title/UUID/URL cá nhân vào report.
  Credentials A/B chưa được cung cấp: chưa xác thực owner, chưa kiểm tra
  private visibility A→B/guest, B→A/guest, hoặc account switch trên live UI.
  Không tạo fixture thật để bù. Không mở nguồn Facebook qua tài khoản thật.
- Harness GET-only ban đầu sai tên argument của Requests (`TypeError`);
  sửa harness rồi đọc thành công, không thay đổi repository/runtime.

## Offline/mock và regression model thật

Từ repo root, dùng `PYTHON_DOTENV_DISABLED=1`; các lần pytest tạo `--basetemp`
mới và tắt cache provider. Kiểm tra bình thường bỏ `SEARCH_SEMANTIC_MODEL`.
Full suite cần dependencies trong `requirements-web.txt` và
`requirements-mockweb.txt`; browser runners dùng Playwright và Edge đã cài.
Chỉ chạy launcher mock bằng tay không cần cài Playwright. Model và dependencies
optional được thiết lập riêng như guide; máy đo đã có sẵn, không cài lại.

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
Remove-Item Env:SEARCH_SEMANTIC_MODEL -ErrorAction SilentlyContinue
$runTemp = Join-Path $env:TEMP ('search-demo-tests-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q --tb=short -p no:cacheprovider --basetemp=$runTemp
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.run_keyword --check
$env:SEARCH_SEMANTIC_MODEL = "$env:LOCALAPPDATA\SmartCalendar\models\multilingual-e5-small"
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.check_prepared --output fixtures/search_semantic/hybrid_integrated_report.json
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_demo.verify_ui
```

- Keyword baseline tái lập byte-identical: **1/3 tuning**, **0/4 held-out**,
  **0/4 unrelated false hits**, **0 correctness violations**.
- Real-model `hybrid_integrated_report.json`: **3/3 tuning**, **1/4 held-out**,
  **0/4 unrelated false hits**, **0 violations**. Cả **31 complete ordered
  result sets** giữ nguyên so với reference và historical top-three. H-X02
  và H-V05 đều chỉ có public `33333333-3333-4333-8333-333333333333`, rank 1.
  Đây là **regression verification**, không phải blind evaluation mới.
- Model startup của regression runner: **2.124 s**; evaluation reference +
  prepared: **8.628 s**. Mọi inference đều local.
- Focused mapper/loader/matcher/semantic/client/Supabase/demo: **84 tests và
  512 subtests passed, 0 failed/errors/skipped, 40.66 s**. Một lệnh đầu gõ sai
  tên file semantic không collect test; lệnh sửa chạy đầy đủ. Thêm guard
  fallback so sánh đủ 31 case khi model path không tồn tại: **1 passed, 1.01 s**.
- Focused browser semantic, feedback/badge, preliminary, compact popover,
  Supabase open/Sync: **12 passed, 139.00 s**, không fail/error/skip.
- Full collection **256**: giữ 253 case của F, thêm **2 desktop/narrow
  course/week tests + 1 frozen fallback test**, không mất test.
- **Full offline suite cuối:** **256 passed + 512 subtests passed**, **0 failed,
  0 errors, 0 skipped**, **409.43 s**. JUnit ghi 768 tests gồm subtests. Có 48
  warning Pydantic `BaseTask.model_fields` sẵn có; không sửa ngoài scope Search.
  Lệnh thực tế như trên, thêm `--junitxml=$env:TEMP\commit7-full.xml`; stdout
  lưu `commit7-full.txt`. Keyword check chạy lại sau full suite vẫn byte-identical.

`verify_ui` khởi chạy chính launcher demo, đăng nhập mock rồi dùng controls thật
ở **1280×900 và 390×844**: exact lookup, Enter, 5/≥5/>5, nguồn localhost mở đúng
đích, Clear về idle, paraphrase `hạn cuối đóng học phí` → public `111…111`
**rank 1**, keyword **0 hit** trên 15-row demo. Ảnh closed/popover/dialog đã xem
ở cả hai kích thước; controls nằm trong viewport và dialog đọc được. Browser
runner đợi kết quả query hiện tại, không dùng count còn lại của query trước;
ảnh chụp tắt animation để không ghi frame chuyển cảnh.

`tests/test_search_demo.py` kiểm tra tuần **30/11–06/12 inclusive**, ba scoped
key C/B/G trong guide: **C,B,G → G,B,C → B,C,G**, membership không đổi,
original deadline/source, popup đích kiểm soát, focus và **0 task reads**.
Các regression sẵn có kiểm tra idle, lỗi/success-empty/pending, source disable,
point aliases, private collision, logout/expiry/account switch khi preparation
pending, stale dialog, keyboard/Escape/scroll, Calendar/Agenda/Schedule độc lập.
Pagination >1,000 và originals trước/sau scheduling được xác minh bằng mocked
Supabase qua `test_task_retention.py` / `test_task_retention_ui.py`, không phải
live permission hay scheduling thật.

## Đo mới trên build tích hợp (không thay thế số lịch sử P)

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m fixtures.search_semantic.preparation_benchmark --warm-queries --output fixtures/search_semantic/preparation_integrated.json
```

Chạy riêng, tuần tự, model thật CPU/2 threads, Edge 1440×1000. Cùng workload P:
`benchmark.tasks(14)` và 72 lần lặp UUID5 = **1,008** records. Mỗi scenario một
fresh app/controller/browser, **1 observation**, không phải median/SLA hay cold
disk/boot. Calendar-ready đo `/start` → toolbar visible + socket handshake,
không đo đăng nhập Supabase. Submit-to-final đo marker của query mới + hai RAF.
Preparation duration gồm model setup, hàng đợi, batches và foreground competition.

| Records / scenario | Calendar ready | Preparation complete | Preliminary / searching | Final visible | Foreground passages |
| --- | ---: | ---: | ---: | ---: | ---: |
| 14 / early literal | 1.972 s | 6.067 s | 325 ms | 4.756 s | 13 |
| 14 / early paraphrase | 3.066 s | 5.029 s | 97 ms | 337 ms | 13 |
| 14 / prepared | 2.010 s | 4.493 s | không quan sát | 112 ms | 0 |
| 1,008 / early literal | 1.845 s | 25.307 s | 2,620 ms | 24.006 s | 1,007 |
| 1,008 / early paraphrase | 1.822 s | 26.564 s | 2,449 ms | 24.884 s | 1,007 |
| 1,008 / prepared | 2.713 s | 23.063 s | 269 ms | 325 ms | 0 |

Foreground chỉ encode một query mỗi lượt; model startup fresh-process
**2.376–4.466 s**. Preparation ở early scenarios đã chạy trước lúc submit;
337 ms không có nghĩa cold model chỉ tốn 337 ms. Prepared background encode
14/1,008 passages; early background encode một passage rồi foreground bổ sung.
Trên prepared snapshot, query **khác** `tìm chỗ làm lập trình` rồi submit lại:

| Records | Different query | Repeat | Query inference (different / repeat) |
| --- | ---: | ---: | ---: |
| 14 | 78 ms | 74 ms | 8.75 / 9.91 ms |
| 1,008 | 403 ms | 376 ms | 11.55 / 9.95 ms |

Mỗi lượt warm encode **1 query, 0 passages, 0 task reads**. Tất cả six scenario
và details đều **0 extra task reads**. Complete ordered keys được giữ trong
JSON, trùng `preparation_after.json` cho sáu scenario; different/repeat cũng
trùng thứ tự. Historical reports không sửa.

Giới hạn demo: early search 1,008-row vẫn mất ~25 s, và feedback ~2.5 s trong
lần đo này (chậm hơn quan sát lịch sử ~1 s); prepared ~0.3–0.4 s. Đây là một
lượt đo trên runtime giữ nguyên, không đủ kết luận merge gây regression.
Chưa thử timing live A/B. Chờ preparation trước demo lớn; performance tuning
khác cần review riêng, không đổi ranking/runtime trong Commit 7.

## Handoff ban đầu (trước khi được cấp credentials A/B)

**Direct live:** chỉ guest/public repository như trên. **Offline/mock:** regression,
model thật trên dữ liệu hư cấu, UI và timing. **Team-reported:** chưa có feedback
paraphrase mới, Long layout review hay Hiển shared-build confirmation cho SHA này.
Không chạy live crawler/scheduler/server, không tạo/sửa/xóa/reschedule live task.
Model có sẵn được tái sử dụng, không cài dependency mới; mock servers tự dừng.
Live A/B và các xác nhận đồng đội còn pending; không gọi mock là bằng chứng RLS.

**Đánh giá ban đầu — Ready to commit: No** — offline/mock và model regression đã pass; verification
live A/B (owner isolation, private details và account switch) còn bị chặn do
thiếu credentials. Long layout review, Hiển shared-build confirmation và feedback
paraphrase mới chưa được cung cấp cho build này. Các thay đổi test/demo đã sẵn
sàng review nhưng chưa đủ bằng chứng để gọi toàn bộ Commit 7 hoàn tất.

## Live A/B follow-up — 27/11/2026

Credentials được cấp sau handoff ban đầu. Kiểm tra trên cùng SHA `5ad961d`,
không đổi runtime. Chạy client NiceGUI tạm thời trên loopback, public client key,
đăng nhập qua controls thật. Guard chỉ cho phép GET tới các bảng cần thiết,
POST sign-in và sign-out session test với `scope=local`; chặn task mutation.
Không chạy `server.py`, crawler, scheduler hay mở đích nguồn cá nhân.

| View | Public rows | Private rows | Export của owner đã xác thực |
| --- | ---: | ---: | ---: |
| Guest qua repository | 23 | không request | — |
| A qua NiceGUI live | 23 | 12 | 12, không thiếu/thừa |
| B qua NiceGUI live | 23 | 0 | 0, không thiếu/thừa |

- Auth `/user` xác nhận hai owner khác nhau; mọi personal/state read mang đúng
  access token và `user_id` của owner. Sources cùng bật. Exact public result
  nhất quán trong guest/A/B.
- A tìm được private original qua popover, chọn full scoped key và mở đúng
  title/source trong dialog. So sánh với snapshot ngay trong memory, không ghi
  dữ liệu riêng tư vào report. B và guest không tìm hoặc lookup được cùng key.
  B còn submit title của A qua controls Search thật; không có scoped key của A
  trong final results, và thử chọn key đó với session hiện tại của B bị từ chối.
- Dùng callback **Log out** của giao diện khi dialog private của A còn mở;
  chuyển sang login rồi đăng nhập B. Details/link cũ biến mất. Gọi lại callback
  lựa chọn với session cũ bị từ chối; snapshot, selection và cache A đều trống,
  kể cả sau khi B tải xong. Preparation lúc probe A pending, B running; logout
  dọn cache của cả hai. Không có private fixture B để kiểm tra reverse direction;
  không suy ra owner từ email/export hoặc tạo task để lấp chỗ trống.
- Tổng **3 public + 2 owner-scoped personal task GETs** (một load mỗi view).
  Query/details của A thêm **0 task reads**; tổng sau query B vẫn **5**, không
  có lần đọc task thêm. State/profile/auth-identity GETs được đếm riêng trong
  JSON. Không có task write/delete/scheduling hoặc request mutation bị thử.
- Hai session test được sign-out riêng, HTTP **204/204**; storage/browser tạm
  được xóa, client test đã dừng. Password không đặt trong shell commands hay
  file credentials mới; không chụp ảnh, trace hoặc log private DOM/response.
- Hai probe đầu chưa hoàn tất do harness: một timeout; diagnostic sau đó tìm
  thấy guard đòi `user_id` từ projection state chỉ chọn
  `id,recurrence,status,compulsory,flexible`. Sửa guard theo query hiện hữu:
  vẫn kiểm tra owner/token trên request và IDs trên response; public/personal
  ownership checks giữ nguyên. **Không sửa production hoặc nới assertion
  Search.** Final probe pass. Evidence cũ giữ ở `live_accounts_initial_probe.json`
  và `live_accounts_projection_probe.json`. Sau đó có một toolbar-readiness
  timeout ở B và một lỗi request của test-control; lưu riêng trong
  `live_accounts_navigation_probe.json` / `live_accounts_control_probe.json`.
  Không thu được nguyên nhân chắc chắn của timeout điều hướng trước đó;
  giả thuyết NiceGUI response deadline 3 s chưa được xác nhận. Một lượt đầy đủ
  đã pass trước các probe bổ sung (`live_accounts_completed_probe.json`).
  Final dùng connection HTTP riêng, mới cho control calls, không đổi browser
  assertions, timeouts hay runtime; cả negative UI check và session checks pass.
  Load snapshot A/B trong final **1,299/1,407 ms**, không có load exceptions;
  đây không phải timing login/model hoặc submit-to-results. Timeout cũ không
  tái hiện trong final và vẫn được giữ như giới hạn quan sát, không gọi là
  regression production đã chẩn đoán hoặc đã sửa.
  Final: `live_accounts_verification.json`.

Đây là **direct live evidence** cho đường đọc Search của ứng dụng, tách biệt
với mock và kiểm tra performance/model trước đó. Full offline **256 tests +
512 subtests passed** vẫn là lần chạy trước trên cùng code; không rerun full
suite chỉ vì thêm report/docs. Runtime và frozen artifacts giữ nguyên.
Không có thêm team-reported review; Long/Hiển và feedback paraphrase mới vẫn pending.

**Đánh giá hiện tại — Ready to commit: Yes** — offline/model/UI và các live checks
có fixture đều pass. Giới hạn còn lại: B chưa có private fixture để thử chiều
ngược, live latency chưa đo, và các review đồng đội chưa được cung cấp. Đây là
handoff để review/commit, không phải xác nhận đã release hay có Commit 7 SHA.
