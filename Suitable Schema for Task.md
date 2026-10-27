# THIẾT KẾ SCHEMA DỮ LIỆU THỐNG NHẤT CHO THỰC THỂ TASK
*(Suitable & Production-Ready Schema for Unified Task Entity)*

---

## 1. Bối Cảnh & Động Lực Thiết Kế

Trong đề tài **Trợ lý ảo thông minh cho sinh viên CNTT (Smart Virtual Assistant)**, hệ thống phải xử lý và lưu trữ thông tin đa dạng từ nhiều nguồn:
* Moodle LMS (Bài tập về nhà, đồ án, hạn nộp).
* Cổng thông tin đào tạo / Website trường (Lịch học TKB, lịch thi, thông báo học phí).
* Fanpage / Nhóm Đoàn - Hội (Sự kiện phong trào, hội thảo học thuật kiếm Điểm Rèn Luyện).
* Người dùng tự nhập (Lịch hẹn cá nhân, lịch làm thêm, giờ ngủ, sinh hoạt).

### 1.1. Tại sao lựa chọn kiến trúc Bảng Thống Nhất (Single Unified Task Table)?
Thay vì phân mảnh thành nhiều bảng riêng biệt (`assignments`, `events`, `classes`, `personal_busy`), việc quy tụ mọi hoạt động về một thực thể duy nhất **`Task`** mang lại 3 ưu thế vượt trội:
1. **Tối ưu cho Tìm kiếm Ngữ nghĩa (Vector / Semantic Search)**: Toàn bộ công việc, sự kiện, lịch học đều có thể đánh index vector chung trong cùng một bảng embedding, giúp tính năng hỏi đáp ngôn ngữ tự nhiên (NLP Query) truy vấn nhanh chóng mà không cần JOIN phức tạp.
2. **Giao diện người dùng tập trung (Unified Timeline / UI Feed)**: Calendar và Todo-list trên PySide6 chỉ cần đọc từ một nguồn dữ liệu duy nhất.
3. **Đơn giản hóa đường ống xử lý (Pipeline Simplicity)**: Từ khâu Crawl $\to$ Filter $\to$ Extract $\to$ Dedup chỉ cần xuất ra một kiểu đối tượng duy nhất.

### 1.2. Phân tích sự thiếu hụt của 15 trường ban đầu
Bản đề xuất ban đầu (15 trường) mới chỉ mô tả được phần nào các **sự kiện cố định (Events)**, nhưng **thiếu hoàn toàn các trường phục vụ cho Bài tập linh hoạt (Assignments), Lịch học lặp lại (Timetable) và Bộ lập lịch tối ưu (Scheduler)**:

| Vấn đề của Schema cũ | Hậu quả thực tế | Giải pháp bổ sung |
|---|---|---|
| **Chưa có `estimated_hours`** | Bài tập không có giờ bắt đầu cố định; thiếu trường này thì thuật toán lập lịch (EDF/CP-SAT) không biết phải dành bao nhiêu tiếng để xếp vào lịch. | Thêm `estimated_hours` (số giờ dự kiến cần làm). |
| **Chỉ có `Số đrl` mà thiếu `drl_category`** | Không biết điểm thuộc Điều 1, 2 hay 3, khiến thuật toán không thể áp dụng quy chế trần điểm từng tiêu chí ($\text{Cap}_c$). | Thêm `drl_category` (`dieu_1` đến `dieu_5`). |
| **Thiếu trường `deadline` riêng biệt** | Nhầm lẫn giữa "Hạn đăng ký sự kiện" và "Hạn nộp bài tập / Hạn đóng học phí". | Tách riêng trường `deadline` chính xác đến phút. |
| **Thiếu trường `status`** | Không biết bài tập nào sinh viên đã nộp/làm xong, dẫn đến việc thuật toán tiếp tục xếp việc đã xong vào tuần sau. | Thêm `status` (`active`, `done`, `archived`, `cancelled`). |
| **Thiếu `course_code` (Mã môn)** | Sinh viên không thể lọc bài tập hay truy vấn: *"Môn Mạng máy tính tuần này có gì cần làm?"*. | Thêm `course_code` (ví dụ: `CSC10004`). |
| **Dùng kiểu `date` thay vì `datetime`** | Không thể xác định giờ xung đột lịch trình hay thời gian di chuyển giữa các cơ sở. | Chuẩn hóa toàn bộ mốc thời gian sang **`datetime` (ISO 8601, timezone-aware)**. |
| **Thiếu cơ chế lặp (`recurrence`)** | Buổi học TKB diễn ra 15 tuần liên tục; nếu lưu từng buổi đơn lẻ sẽ làm phình to DB với hàng trăm bản ghi trùng rác. | Thêm `recurrence` (ví dụ: `WEEKLY:MON`). |
| **Thiếu cờ `is_manual`** | Không phân biệt được việc sinh viên tự tạo tay với việc cào tự động; dễ bị ghi đè sau mỗi chu kỳ cào 12h. | Thêm cờ `is_manual` (bảo vệ can thiệp thủ công). |

---

## 2. Bảng Đặc Tả Schema Hoàn Chỉnh (22 Trường)

Bảng schema dưới đây được thiết kế chuẩn mực, đáp ứng 100% mọi loại hoạt động của sinh viên trong một Database SQLite duy nhất:

| STT | Tên trường (Column) | Kiểu dữ liệu | Nullable? | Ý nghĩa & Mô tả chi tiết | Áp dụng cho loại nào? |
|:---:|---|---|:---:|---|---|
| **1** | `id` | `VARCHAR(40)` | **PK** | Khóa chính duy nhất (UUID v4 hoặc SHA-1 Hash từ dedup_key) | Mọi hoạt động |
| **2** | `title` | `VARCHAR(255)` | **NOT NULL** | Tiêu đề hoạt động / Tên môn học / Tên bài tập / Tên sự kiện | Mọi hoạt động |
| **3** | `type` | `VARCHAR(30)` | **NOT NULL** | Loại: `class` (học), `assignment` (bài tập), `exam` (thi), `event` (ĐRL), `personal` (việc riêng), `tuition` (học phí) | Mọi hoạt động |
| **4** | `course_code` | `VARCHAR(20)` | NULL | Mã môn học chuẩn (regex: `[A-Z]{3}\d{5}`, vd: `CSC10004`) | Lịch học, Bài tập, Thi |
| **5** | `description` | `TEXT` | NULL | Mô tả chi tiết, thể lệ cuộc thi hoặc đề bài bài tập | Tùy chọn |
| **6** | `target_audience` | `VARCHAR(100)` | NULL | Đối tượng áp dụng (Toàn trường, Khóa K22, Khoa CNTT...) | Sự kiện ĐRL, Thông báo |
| **7** | `location` | `VARCHAR(100)` | NULL | Địa điểm diễn ra (`CS1`, `CS2`, `Online`, `MS Teams`,... để tính di chuyển) | Lịch học, Sự kiện, Thi |
| **8** | `registration_start` | `DATETIME` | NULL | Thời điểm mở đơn đăng ký tham gia | Sự kiện ĐRL |
| **9** | `registration_end` | `DATETIME` | NULL | Thời điểm đóng đơn đăng ký tham gia | Sự kiện ĐRL |
| **10** | `start_time` | `DATETIME` | NULL | Thời điểm bắt đầu hoạt động (cố định) | Lịch học, Sự kiện, Việc riêng |
| **11** | `end_time` | `DATETIME` | NULL | Thời điểm kết thúc hoạt động (cố định) | Lịch học, Sự kiện, Việc riêng |
| **12** | `deadline` | `DATETIME` | NULL | Hạn chót bắt buộc phải nộp bài / hoàn thành / đóng tiền | Bài tập, Đồ án, Học phí |
| **13** | `estimated_hours` | `FLOAT` | NULL | Thời lượng dự tính cần làm (ví dụ: 2.0h, 3.5h) phục vụ xếp lịch | Bài tập, Đồ án, Ôn thi |
| **14** | `training_points` | `INT` | NULL | Số điểm rèn luyện nhận được nếu tham gia (mặc định: 0) | Sự kiện ĐRL |
| **15** | `drl_category` | `VARCHAR(20)` | NULL | Tiêu chí ĐRL: `dieu_1`, `dieu_2`, `dieu_3`, `dieu_4`, `dieu_5` | Sự kiện ĐRL |
| **16** | `recurrence` | `VARCHAR(50)` | NULL | Quy tắc lặp: `NONE`, `WEEKLY:MON`, `DAILY` (phục vụ TKB, giờ ngủ) | Lịch học TKB, Giờ ngủ |
| **17** | `status` | `VARCHAR(20)` | **NOT NULL** | Trạng thái: `active` (chưa làm), `done` (đã xong), `archived`, `cancelled` | Mọi hoạt động |
| **18** | `is_manual` | `BOOLEAN` | **NOT NULL** | `True` nếu người dùng tự tay tạo/chỉnh sửa (bảo vệ không cho cào đè) | Mọi hoạt động |
| **19** | `source_url` | `TEXT` | NULL | Đường dẫn gốc của bài viết / Link nộp bài trên Moodle | Bài tập, Sự kiện |
| **20** | `source_platform` | `VARCHAR(50)` | **NOT NULL** | Nguồn thu thập: `moodle`, `portal`, `facebook`, `custom` | Mọi hoạt động |
| **21** | `embedding` | `BLOB` / `TEXT` | NULL | Vector ngữ nghĩa (Ví dụ: mảng float 768 chiều từ Gemini) cho NLP | Mọi hoạt động |
| **22** | `updated_at` | `DATETIME` | **NOT NULL** | Thời điểm cập nhật cuối cùng (phục vụ đồng bộ và dedup) | Mọi hoạt động |

---

## 3. Triển Khai Bằng Python (Pydantic v2 Model)

Code Pydantic v2 dưới đây dùng để validate toàn bộ dữ liệu từ tầng Extract/Crawl trước khi ghi xuống SQLite và truyền vào thuật toán lập lịch:

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, model_validator

class TaskType(str, Enum):
    CLASS       = "class"        # Thời khóa biểu học tập trên lớp
    ASSIGNMENT  = "assignment"   # Bài tập về nhà, đồ án, nộp bài Moodle
    EXAM        = "exam"         # Lịch thi, kiểm tra giữa kỳ / cuối kỳ
    EVENT       = "event"        # Sự kiện, hội thảo, phong trào cộng ĐRL
    PERSONAL    = "personal"     # Việc cá nhân (khám bệnh, làm thêm, hẹn bạn)
    TUITION     = "tuition"      # Thông báo hạn nộp học phí

class TaskStatus(str, Enum):
    ACTIVE      = "active"       # Đang cần thực hiện
    DONE        = "done"         # Đã hoàn thành / Đã nộp bài
    ARCHIVED    = "archived"     # Đã hết hạn hoặc lưu trữ
    CANCELLED   = "cancelled"    # Bị hủy bỏ

class DRLCategory(str, Enum):
    DIEU_1 = "dieu_1"  # Ý thức học tập
    DIEU_2 = "dieu_2"  # Ý thức kỷ luật
    DIEU_3 = "dieu_3"  # Hoạt động phong trào, tình nguyện
    DIEU_4 = "dieu_4"  # Phẩm chất công dân, quan hệ cộng đồng
    DIEU_5 = "dieu_5"  # Thành tích xuất sắc, khen thưởng đặc biệt

class SourcePlatform(str, Enum):
    MOODLE   = "moodle"
    PORTAL   = "portal"
    FACEBOOK = "facebook"
    CUSTOM   = "custom"

class Task(BaseModel):
    id: str = Field(..., description="Khóa chính duy nhất (UUID hoặc Hash SHA-1)")
    title: str = Field(..., min_length=2, max_length=300, description="Tiêu đề hoạt động")
    type: TaskType = Field(..., description="Loại hoạt động")
    course_code: str | None = Field(default=None, regex=r"^[A-Z]{3}\d{5}$", description="Mã môn học")
    description: str | None = Field(default=None, description="Mô tả chi tiết")
    target_audience: str | None = Field(default=None, description="Đối tượng tham gia")
    location: str | None = Field(default=None, description="Địa điểm diễn ra (CS1, CS2, Online...)")
    
    # Các mốc thời gian chuẩn hóa datetime
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    deadline: datetime | None = None
    
    # Phục vụ lập lịch & Tối ưu hóa
    estimated_hours: float | None = Field(default=None, ge=0.25, le=40.0, description="Số giờ cần để làm")
    training_points: int | None = Field(default=0, ge=0, le=100, description="Điểm rèn luyện")
    drl_category: DRLCategory | None = None
    recurrence: str | None = Field(default=None, description="Quy tắc lặp (vd: WEEKLY:MON)")
    
    # Quản lý trạng thái & Nguồn
    status: TaskStatus = Field(default=TaskStatus.ACTIVE)
    is_manual: bool = Field(default=False, description="True nếu do user tự thêm/sửa tay")
    source_url: str | None = None
    source_platform: SourcePlatform = Field(default=SourcePlatform.CUSTOM)
    embedding: list[float] | None = None
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_task_logic(self):
        # 1. Ràng buộc thời gian cố định: start_time phải nhỏ hơn end_time
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValueError("start_time phải diễn ra trước end_time")
                
        # 2. Bài tập bắt buộc phải có deadline
        if self.type in (TaskType.ASSIGNMENT, TaskType.TUITION) and not self.deadline:
            raise ValueError(f"Hoạt động loại {self.type.value} bắt buộc phải có deadline")
            
        # 3. Sự kiện ĐRL có điểm thì nên có tiêu chí
        if self.training_points and self.training_points > 0 and not self.drl_category:
            self.drl_category = DRLCategory.DIEU_3 # Mặc định phong trào nếu thiếu
            
        return self
```

---

## 4. Triển Khai SQL DDL (SQLite Database Schema)

Câu lệnh tạo bảng và index tối ưu trong SQLite:

```sql
-- 1. BẢNG DỮ LIỆU THỐNG NHẤT TASK
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(40) PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    type VARCHAR(30) NOT NULL,
    course_code VARCHAR(20),
    description TEXT,
    target_audience VARCHAR(100),
    location VARCHAR(100),
    
    -- Mốc thời gian (Lưu chuẩn chuỗi ISO 8601: YYYY-MM-DDTHH:MM:SS)
    registration_start DATETIME,
    registration_end DATETIME,
    start_time DATETIME,
    end_time DATETIME,
    deadline DATETIME,
    
    -- Lập lịch & ĐRL
    estimated_hours REAL,
    training_points INTEGER DEFAULT 0,
    drl_category VARCHAR(20),
    recurrence VARCHAR(50),
    
    -- Trạng thái & Quyền sở hữu
    status VARCHAR(20) DEFAULT 'active' NOT NULL,
    is_manual INTEGER DEFAULT 0 NOT NULL, -- 0: false, 1: true
    source_url TEXT,
    source_platform VARCHAR(50) NOT NULL,
    embedding BLOB,                        -- Lưu vector dạng binary hoặc chuỗi JSON
    updated_at DATETIME NOT NULL
);

-- 2. HỆ THỐNG INDEXES TỐI ƯU TRUY VẤN
-- Tối ưu cho Scheduler: Quét nhanh các task đang active cần xếp lịch
CREATE INDEX IF NOT EXISTS idx_tasks_status_type ON tasks(status, type);

-- Tối ưu cho EDF (Earliest Deadline First): Sắp xếp việc theo deadline tăng dần
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline) WHERE deadline IS NOT NULL;

-- Tối ưu cho Thời khóa biểu / Lịch tuần: Lấy các sự kiện/buổi học theo mốc bắt đầu
CREATE INDEX IF NOT EXISTS idx_tasks_start_time ON tasks(start_time) WHERE start_time IS NOT NULL;

-- Tối ưu cho NLP Query / Lọc theo môn học
CREATE INDEX IF NOT EXISTS idx_tasks_course ON tasks(course_code) WHERE course_code IS NOT NULL;
```

---

## 5. Ma Trận Ánh Xạ Đa Hình (Polymorphism Mapping Matrix)

Để chứng minh tính khả thi của việc **dùng chung 1 bảng**, dưới đây là bảng ma trận chỉ rõ giá trị các trường đối với từng loại công việc thực tế:

| Tên trường | 1. Lịch học TKB (`class`) | 2. Bài tập Moodle (`assignment`) | 3. Sự kiện ĐRL (`event`) | 4. Việc cá nhân (`personal`) | 5. Học phí (`tuition`) |
|---|---|---|---|---|---|
| `title` | Nhập môn Lập trình | Lab 3: Cấu trúc dữ liệu | Tọa đàm Khoa học AI | Khám răng định kỳ | Học phí HK1/2026 |
| `type` | `class` | `assignment` | `event` | `personal` | `tuition` |
| `course_code` | `CSC10001` | `CSC10002` | `NULL` | `NULL` | `NULL` |
| `location` | `CS1 - Tòa F` | `NULL` | `CS2 - Giảng đường 1` | `Nha khoa Q5` | `Online` |
| `start_time` | `07:30:00` | `NULL` | `14:00:00` | `09:00:00` | `NULL` |
| `end_time` | `11:00:00` | `NULL` | `16:30:00` | `10:30:00` | `NULL` |
| `deadline` | `NULL` | `2026-10-30 23:59:00` | `NULL` | `NULL` | `2026-11-15 17:00:00` |
| `estimated_hours` | `NULL` | `3.0` tiếng | `NULL` | `NULL` | `NULL` |
| `training_points` | `0` | `0` | `5` | `0` | `0` |
| `drl_category` | `NULL` | `NULL` | `dieu_1` | `NULL` | `NULL` |
| `recurrence` | `WEEKLY:MON` | `NULL` | `NONE` | `NONE` | `NONE` |
| `is_manual` | `0` (hoặc `1`) | `0` | `0` | `1` (User tự tạo) | `0` |
| `status` | `active` | `active` (hoặc `done`) | `active` | `active` | `active` |
| `source_platform` | `portal` | `moodle` | `facebook` | `custom` | `portal` |

> **Nhận xét**: 
> * SQLite lưu trữ các trường mang giá trị `NULL` dưới dạng cờ header chỉ tốn đúng **0 byte** dữ liệu thực.
> * Gom chung 1 bảng không hề làm tốn dung lượng ổ đĩa, nhưng giúp code Python cực kỳ tinh gọn, không phải quản lý nhiều model riêng lẻ.

---

## 6. Phân Tích Thiết Kế Schema Dưới Góc Nhìn Tư Duy Tính Toán (Computational Thinking)

Để giải quyết bài toán quản lý và tự động tối ưu hóa lịch biểu sinh viên, việc hợp nhất toàn bộ hoạt động vào **một thực thể `Task` duy nhất với 22 trường thuộc tính** không phải là quyết định ngẫu nhiên, mà là kết quả của việc áp dụng chặt chẽ 3 trụ cột nền tảng của **Tư duy tính toán (Computational Thinking)**:

---

### Trụ cột 1: Trừu tượng hóa (Abstraction) — Tại sao quy mọi hoạt động về một thực thể `Task`?

Trừu tượng hóa là quá trình loại bỏ các chi tiết ngữ cảnh rườm rà, tập trung vào bản chất cốt lõi của bài toán trong mô hình tính toán.

1. **Bản chất cạnh tranh tài nguyên hữu hạn (Resource Contention Abstraction):**
   * *Ngữ cảnh thực tế:* Sinh viên có nhiều hoạt động mang tên gọi và ngữ nghĩa khác nhau: đi học trên giảng đường, nộp bài tập Moodle, tham gia hội thảo kiếm ĐRL, đi khám răng, nộp học phí.
   * *Bản chất tính toán:* Dưới góc nhìn hệ thống, toàn bộ các hoạt động trên đều cùng cạnh tranh một loại tài nguyên khan hiếm duy nhất: **Quỹ thời gian của một cá nhân ($T \in [0, 24\text{h}/\text{ngày}]$)**. Dù mang tên gọi là gì, một con người không thể cùng lúc ngồi học ở Cơ sở 1 và dự hội thảo ở Cơ sở 2.
   * *Mô hình hóa:* Thay vì tạo các bảng riêng biệt (`Classes`, `Assignments`, `Events`, `PersonalNotes`), ta trừu tượng hóa chúng thành các **khoảng thời gian (Intervals)** trên trục số thực:
     $$I_i = [\text{start}_i, \text{end}_i]$$
     Việc hợp nhất thành một thực thể `Task` cho phép mô hình toán học CP-SAT áp dụng ràng buộc duy nhất `AddNoOverlap` trên một mảng tập hợp chung thay vì phải xử lý ma trận giao cắt giữa nhiều bảng dữ liệu khác nhau.

2. **Chuẩn hóa giao diện dữ liệu (Unified Data Contract):**
   * Toàn bộ pipeline hệ thống (Crawler $\rightarrow$ Trích xuất LLM $\rightarrow$ Lưu trữ SQLite $\rightarrow$ Vector Search RAG $\rightarrow$ Bộ giải CP-SAT $\rightarrow$ Giao diện PySide6) chỉ cần làm việc với **một kiểu dữ liệu duy nhất (`TaskSchema`)**.
   * Loại bỏ hoàn toàn sự phức tạp của các câu lệnh đa bảng (`JOIN`, `UNION`), giảm độ trễ truy vấn I/O từ $O(k \cdot \log N)$ xuống $O(\log N)$ trên một bảng duy nhất có lập chỉ mục (index).

---

### Trụ cột 2: Phân rã bài toán (Decomposition) — Tại sao lại cần phân rã thành đúng 22 trường dữ liệu?

Phân rã là việc chia tách một bài toán lớn, phức tạp thành các thành phần con độc lập, nguyên tử (atomic) và có thể quản lý được. Để một `Task` đáp ứng trọn vẹn vòng đời từ thu thập tự động, lưu trữ, suy luận ngữ nghĩa đến lập lịch tối ưu, 22 trường thuộc tính được phân rã thành 6 nhóm chức năng nguyên tử:

```
                            ┌──────────────────────────────────────────────┐
                            │      THỰC THỂ HỢP NHẤT: TASK (22 TRƯỜNG)     │
                            └──────────────────────┬───────────────────────┘
         ┌──────────────────┬──────────────────────┼──────────────────────┬──────────────────┐
         ▼                  ▼                      ▼                      ▼                  ▼
┌─────────────────┐┌─────────────────┐   ┌───────────────────┐  ┌──────────────────┐┌──────────────────┐
│ 1. ĐỊNH DANH &  ││ 2. KHÔNG-GIỜ   │   │ 3. ĐIỀU KHIỂN     │  │ 4. VÒNG ĐỜI &    ││ 5. TRUY XUẤT     │
│    SIÊU DỮ LIỆU ││    CỐ ĐỊNH      │   │    LẬP LỊCH & ĐRL │  │    ĐỒNG BỘ        ││    THÔNG MINH    │
│                 ││                 │   │                   │  │                  ││    (RAG / VECTOR)│
│ • id            ││ • start_time    │   │ • deadline        │  │ • status         ││ • embedding      │
│ • title         ││ • end_time      │   │ • estimated_hours │  │ • recurrence     ││ • target_audience│
│ • type          ││ • location      │   │ • training_points │  │ • is_manual      ││ • updated_at     │
│ • course_code   ││                 │   │ • drl_category    │  │ • source_platform││                  │
│ • description   ││                 │   │ • registration_   │  │ • source_url     ││                  │
│                 ││                 │   │   start/end       │  │                  ││                  │
└─────────────────┘└─────────────────┘   └───────────────────┘  └──────────────────┘└──────────────────┘
```

#### Phân tích sự cần thiết của các trường bổ sung so với schema 15 trường ban đầu:
Schema 15 trường ban đầu chỉ đủ cho việc hiển thị bảng tin (Bulletin Board), nhưng hoàn toàn **bế tắc** khi đưa vào hệ thống tính toán tự động:

1. **`estimated_hours` (Thời lượng ước tính):** 
   * *Vấn đề:* Bài tập và ôn thi không có `start_time` và `end_time` cố định trước; chúng chỉ có hạn chót (`deadline`). Nếu không có trường này, thuật toán lập lịch không thể biết cần phân bổ khối thời gian dài bao nhiêu tiếng (ví dụ: chia thành các block 90 phút) vào các khoảng trống trong tuần.
2. **`drl_category` (Khoản mục quy chế ĐRL):**
   * *Vấn đề:* Quy chế rèn luyện HCMUS áp dụng trần điểm phụ thuộc từng điều khoản cụ thể ($\text{Cap}_c \in \{20, 25, 10\}$ điểm). Nếu chỉ có số điểm `training_points` mà thiếu nhóm quy chế, thuật toán sẽ phạm sai lầm xếp dồn toàn bộ sự kiện dễ vào Điều 1 và làm vượt trần vô ích (vi phạm hàm mục tiêu cực đại hóa điểm thực tế).
3. **`deadline` (Hạn chót hoàn thành):**
   * *Vấn đề:* Tách biệt rạch ròi giữa hạn chót hoàn thành công việc (`deadline`) với ngày hết hạn đăng ký sự kiện (`registration_end`). Việc gộp chung sẽ gây nhầm lẫn nghiêm trọng trong thuật toán lập lịch theo thời hạn (EDF).
4. **`status` (Trạng thái công việc):**
   * *Vấn đề:* Phân rã vòng đời của tác vụ (`active`, `done`, `archived`, `cancelled`). Tránh việc bộ lập lịch tính toán lại cả những bài tập sinh viên đã nộp hoặc các sự kiện đã kết thúc.
5. **`course_code` (Mã môn học chuẩn hóa):**
   * *Vấn đề:* Phân rã ngữ cảnh học phần (ví dụ `CSC10001`). Cho phép lọc, gộp và lập lịch ôn tập tương thích với thời khóa biểu; đồng thời hỗ trợ AI trả lời chính xác các câu hỏi như: *"Tuần này môn Kiến trúc máy tính có bài tập gì không?"*.
6. **`recurrence` (Quy luật lặp lại):**
   * *Vấn đề:* Thời khóa biểu lặp lại đều đặn 15 tuần. Thay vì sinh ra 15 bản ghi nhân bản làm phình to cơ sở dữ liệu ($15 \times N$), ta phân rã thành một bản ghi duy nhất đi kèm biểu thức chu kỳ (`WEEKLY:MON`).
7. **`is_manual` (Cờ phân định quyền chỉnh sửa):**
   * *Vấn đề:* Bảo vệ tính toàn vẹn dữ liệu. Khi crawler chạy định kỳ (mỗi 12 tiếng), cờ này giúp hệ thống nhận diện và không bao giờ ghi đè hoặc xóa các công việc cá nhân do chính sinh viên tự tay tạo lập (`is_manual = 1`).

---

### Trụ cột 3: Nhận dạng quy luật (Pattern Recognition) — Nhận diện sự đồng nhất giữa các hoạt động

Nhận dạng quy luật giúp phát hiện các cấu trúc tương đồng ẩn sau các hiện tượng bề ngoài khác biệt, từ đó áp dụng các giải pháp kiến trúc tối ưu đã được kiểm chứng.

1. **Khuôn mẫu phân loại nhị phân thời gian (Temporal Polymorphism Pattern):**
   * Quan sát mọi hoạt động của sinh viên đại học, ta nhận diện được quy luật toán học cốt lõi: Tất cả chỉ quy về **2 loại khuôn mẫu thời gian**:
     * **Khuôn mẫu Cố định (Fixed-Interval Events):** Có mốc bắt đầu và kết thúc cố định trên trục thời gian ($\exists t_{\text{start}}, t_{\text{end}}$). Thuộc nhóm này gồm: Lịch học trên lớp, hội thảo ĐRL, lịch thi, việc hẹn cá nhân. Các công việc này đóng vai trò là **vật cản cứng (Hard Obstacles)** trên lịch.
     * **Khuôn mẫu Linh hoạt (Floating Deadline Tasks):** Không có mốc bắt đầu cố định, chỉ có thời lượng và hạn chót ($\exists \text{duration}, \text{deadline}$). Thuộc nhóm này gồm: Bài tập Moodle, ôn thi, đồ án môn học, đóng học phí. Các công việc này là **khối lưu động (Floating Blocks)** cần thuật toán tìm khoảng trống để lấp vào.
   * *Hệ quả kiến trúc:* Nhận diện quy luật này cho phép schema 22 trường dùng chung các cột thời gian: Sự kiện cố định thì điền `start_time`/`end_time`, tác vụ linh hoạt thì điền `estimated_hours`/`deadline`.

2. **Khuôn mẫu thiết kế cơ sở dữ liệu (Single Table Inheritance - STI):**
   * Nhận diện đặc tính truy vấn của trợ lý ảo sinh viên: Thường truy vấn từ giao diện hoặc chatbot là truy vấn theo chiều thời gian (Time-series Query): *"Hôm nay tôi phải làm gì?"*, *"Tuần này có những sự kiện nào?"*.
   * Thay vì phân mảnh dữ liệu thành nhiều bảng dẫn đến câu lệnh truy vấn phức tạp tốn chi phí kết nối bảng (`JOIN`), mô hình **Single Table Inheritance** gom toàn bộ vào một bảng phẳng duy nhất. Nhờ cơ chế lưu trữ của SQLite (các giá trị `NULL` chỉ tốn cờ bit 0 byte), giải pháp này vừa tối ưu dung lượng đĩa, vừa tối đa tốc độ đọc dữ liệu.

3. **Khuôn mẫu tối ưu hóa toán học (Submodular Knapsack Pattern):**
   * Hoạt động săn Điểm rèn luyện của sinh viên tuân theo đúng khuôn mẫu toán học của bài toán **Balo đa chiều với ràng buộc cận trên từng ngăn (Multi-dimensional Knapsack with Category Caps)**.
   * Việc thiết kế cặp trường `training_points` và `drl_category` trực tiếp chuyển hóa bài toán đời thực thành mô hình toán chuẩn tắc:
     $$\max \sum_{c} \min \left( \text{Cap}_c, \sum_{i \in \text{Task}_c} x_i \cdot p_i \right)$$
     giúp bộ giải toán nhận diện cấu trúc bài toán ngay lập tức mà không cần qua tầng tiền xử lý trung gian phức tạp.

4. **Khuôn mẫu đồng bộ hóa bất biến (Idempotent Synchronization Pattern):**
   * Quá trình đồng bộ dữ liệu từ các cổng thông tin (Moodle, Web Khoa, Mạng xã hội) lặp lại liên tục theo chu kỳ.
   * Sự kết hợp của `source_platform`, `source_url` và `updated_at` tạo thành mẫu khóa nhận diện idempotent: Nếu một thông báo sự kiện được quét lại, hệ thống nhận diện được bản ghi đã tồn tại để thực hiện cập nhật (`UPSERT`) thay vì chèn trùng lặp, bảo đảm tính toàn vẹn của lịch biểu.
