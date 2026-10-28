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
    DIEU_1 = "dieu_1"  # Tham gia học tập và nghiên cứu khoa học (Tối đa: 30 điểm)
    DIEU_2 = "dieu_2"  # Chấp hành nội quy, quy chế và các quy định (Tối đa: 20 điểm)
    DIEU_3 = "dieu_3"  # Hoạt động CT-XH, VH-VN, TD-TT; phòng chống tội phạm, tệ nạn (Tối đa: 25 điểm)
    DIEU_4 = "dieu_4"  # Hành động hướng đến xây dựng và phát triển cộng đồng (Tối đa: 25 điểm)
    DIEU_5 = "dieu_5"  # Các nội dung khuyến khích (Tối đa: 30 điểm)

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

### Trụ Cột 1: Trừu Tượng Hóa (Abstraction) — Tại sao quy mọi hoạt động về một thực thể `Task`?

Trừu tượng hóa là bước đi khởi đầu nhằm **loại bỏ các chi tiết ngữ cảnh rườm rà** để nắm bắt bản chất cốt lõi của bài toán trước khi sa đà vào các thuộc tính vụn vặt.

1. **Lược bỏ lớp vỏ cảm tính đời thường:**
   * Khi đứng trước thông tin thực tế: Buổi học môn Giải tích trên giảng đường, Bài tập Lab 3 trên Moodle, Tọa đàm khoa học kiếm 5 ĐRL, Hạn nộp học phí, hay Lịch hẹn khám răng.
   * Nếu tiếp cận ngây thơ (chưa qua trừu tượng hóa), ta sẽ bị cuốn vào ngữ nghĩa đời thường: *"Học tập khác với đi chơi, hội thảo khác với bài tập"* $\to$ Dẫn đến sai lầm tạo ra hàng loạt bảng dữ liệu rời rạc (`Classes`, `Assignments`, `Events`).

2. **Nhìn thấu bản chất toán học (Resource Contention Abstraction):**
   * Dưới góc nhìn hệ thống tính toán, toàn bộ các hoạt động trên đều cùng cạnh tranh một loại tài nguyên hữu hạn và độc quyền duy nhất: **Quỹ thời gian của một cá nhân ($T \in [0, 24\text{h}/\text{ngày}]$)**.
   * Một con người tại một thời điểm chỉ có thể làm một việc duy nhất. Dù mang tên gọi là gì, bản chất của chúng đều chỉ là: **Một yêu cầu phân bổ trên trục thời gian (A Time-Allocation Request)**.

👉 **Cú nhảy Trừu tượng hóa**: 
Hệ thống không cần phân mảnh theo tên gọi đời thường, mà mô hình hóa toàn bộ các hoạt động thành một thực thể trừu tượng duy nhất đặt tên là **`Task`**. Toàn bộ đường ống xử lý (Crawler $\to$ SQLite $\to$ AI Search $\to$ Lập lịch CP-SAT $\to$ UI PySide6) chỉ cần làm việc với một giao diện dữ liệu thống nhất (`TaskSchema`).

---

### Trụ Cột 2: Phân Rã (Decomposition) — Tại sao lại cần đúng 22 trường thuộc tính?

Sau khi đã trừu tượng hóa thành thực thể `Task`, bước tiếp theo là **Phân rã**: *"Để thực thể `Task` này có thể sống, luân chuyển và vận hành trơn tru qua toàn bộ 4 phân hệ của trợ lý ảo, nó bắt buộc phải chứa những thông tin nguyên tử nào?"*

Ta phân rã thực thể `Task` theo **4 chiều không gian chức năng** của hệ thống:

```
                          THỰC THỂ TRỪU TƯỢNG: TASK
                                     │
     ┌──────────────────┬────────────┴────────┬──────────────────┐
     ▼                  ▼                     ▼                  ▼
┌─────────────────┐┌─────────────────┐  ┌───────────────────┐  ┌──────────────────┐
│ 1. CHIỀU ĐỒNG BỘ││ 2. CHIỀU NGỮ    │  │ 3. CHIỀU TOÁN HỌC │  │ 4. CHIỀU TRẠNG   │
│    & ETL        ││    NGHĨA & AI   │  │    & LẬP LỊCH     │  │    THÁI & GIAO   │
│ (5 trường)      ││ (5 trường)      │  │ (9 trường)        │  │    DIỆN (3 trường│
└─────────────────┘└─────────────────┘  └───────────────────┘  └──────────────────┘
```

1. **Chiều 1: Quản trị nạp & Đồng bộ dữ liệu (ETL / 5 trường)**:
   * *Định danh duy nhất, chống trùng lặp:* $\to$ **`id`** (UUID / SHA-1 hash).
   * *Nguồn gốc dữ liệu & Đường dẫn xem chi tiết:* $\to$ **`source_platform`**, **`source_url`**.
   * *Mốc thời gian crawl & Cờ bảo vệ dữ liệu người dùng tự nhập không bị ghi đè:* $\to$ **`updated_at`**, **`is_manual`**.
2. **Chiều 2: Nhận thức & Khám phá thông tin (RAG / 5 trường)**:
   * *Nội dung ngữ nghĩa:* $\to$ **`title`**, **`description`**.
   * *Ngữ cảnh môn học & Đối tượng thụ hưởng:* $\to$ **`course_code`**, **`target_audience`**.
   * *Vector toán học để AI truy vấn ngôn ngữ tự nhiên:* $\to$ **`embedding`**.
3. **Chiều 3: Điều phối tài nguyên & Lập lịch toán học (CP-SAT / 9 trường)**:
   * *Không gian địa lý để tính thời gian di chuyển giữa các cơ sở:* $\to$ **`location`**.
   * *Khung thời gian cố định & Khung đăng ký sự kiện:* $\to$ **`start_time`**, **`end_time`**, **`registration_start`**, **`registration_end`**.
   * *Khối lượng thời gian cần thiết & Hạn chót cho task linh hoạt:* $\to$ **`estimated_hours`**, **`deadline`**.
   * *Điểm thưởng & Tiêu chí quy chế 5 Điều để kiểm soát trần $\text{Cap}_c$:* $\to$ **`training_points`**, **`drl_category`**.
4. **Chiều 4: Vòng đời & Trạng thái tương tác (Lifecycle / 3 trường)**:
   * *Phân loại nghiệp vụ:* $\to$ **`type`**.
   * *Tiến độ hoàn thành để solver không xếp lại việc đã làm:* $\to$ **`status`**.
   * *Biểu thức lặp chu kỳ để tránh phình to CSDL:* $\to$ **`recurrence`**.

👉 **Kết quả Phân rã**:
$$\mathbf{5\text{ (Đồng bộ)}} + \mathbf{5\text{ (Ngữ nghĩa)}} + \mathbf{9\text{ (Lập lịch)}} + \mathbf{3\text{ (Vòng đời)}} = \mathbf{22\text{ trường thuộc tính}}.$$
*Mỗi trường là một thành phần nguyên tử bắt buộc; thiếu 1 trường thì một phân hệ chức năng sẽ bị gãy vỡ, thừa 1 trường thì phát sinh dữ liệu rác không phục vụ mục đích tính toán nào.*

---

### Trụ Cột 3: Nhận Dạng Quy Luật (Pattern Recognition) — Tối ưu hóa kiến trúc tổ chức dữ liệu

Sau khi đã trừu tượng hóa thành thực thể `Task` và phân rã ra 22 trường, câu hỏi kiến trúc xuất hiện: *"Liệu việc gom 22 trường vào chung 1 bảng duy nhất có gây lãng phí dung lượng hay suy giảm hiệu năng không?"* 

Trụ cột **Nhận dạng quy luật** giúp phát hiện các mẫu hình đã được chứng minh trong khoa học máy tính:

1. **Quy luật Đa hình Không-Thời gian (Temporal Polymorphism Pattern):**
   * Nhận diện quy luật đối ngẫu giữa các trường thời gian:
     * Task cố định (`class`, `event`) $\to$ điền `start_time/end_time`, để trống `deadline/estimated_hours`.
     * Task linh hoạt (`assignment`, `exam`) $\to$ điền `deadline/estimated_hours`, để trống `start_time/end_time`.
   * Quy luật này cho thấy 22 trường hoàn toàn tương thích và bổ trợ cho nhau mà không hề gây xung đột cấu trúc.

2. **Quy luật Kế thừa bảng đơn (Single Table Inheritance - STI) trong SQLite:**
   * Trong SQLite, các giá trị mang cờ `NULL` chỉ tốn đúng **0 byte** dữ liệu thực tế.
   * Nhận diện quy luật truy vấn: Sinh viên luôn truy vấn theo dòng thời gian tổng hợp (*"Hôm nay tôi phải làm gì?"*). Gom chung 1 bảng giúp triệt tiêu hoàn toàn các câu lệnh `JOIN`/`UNION` đa bảng phức tạp, giảm độ phức tạp truy vấn từ $O(k \log N)$ xuống $O(\log N)$ trên một cây chỉ mục B-Tree duy nhất.

3. **Quy luật Balo Submodular (Submodular Knapsack Pattern):**
   * Cặp trường `training_points` và `drl_category` khớp chính xác với quy luật lợi ích biên giảm dần khi chạm trần quy chế:
     $$\max \sum_{c} \min \left( \text{Cap}_c, \sum_{i \in \text{Task}_c} x_i \cdot p_i \right)$$
     giúp bộ giải nhận dạng cấu trúc bài toán ngay lập tức mà không cần qua tầng tiền xử lý trung gian phức tạp.

4. **Quy luật Đồng bộ hóa Bất biến (Idempotent Synchronization Pattern):**
   * Bộ ba (`id`, `source_platform`, `updated_at`) tạo thành quy luật cập nhật bảo toàn trạng thái (`UPSERT`), giúp crawler chạy lặp lại định kỳ mà không sinh rác bản ghi.

---

### Bảng Tổng Kết Tiến Trình Suy Luận Kiến Trúc

| Trụ cột Tư duy Tính toán | Luận cứ khoa học | Kết quả thiết kế tất yếu |
|---|---|---|
| **1. Trừu tượng hóa (Abstraction)** | Lược bỏ chi tiết cảm tính; quy mọi hoạt động về mô hình tranh chấp quỹ thời gian cá nhân 24h. | $\implies$ **Hợp nhất toàn bộ hoạt động vào một thực thể duy nhất: `Task`.** |
| **2. Phân rã (Decomposition)** | Bóc tách 4 bài toán kỹ thuật: ETL (5) + RAG (5) + Lập lịch (9) + Vòng đời (3). | $\implies$ **Bắt buộc phải có đúng 22 trường thuộc tính nguyên tử.** |
| **3. Nhận dạng quy luật (Pattern Recognition)** | Nhận diện tính đa hình thời gian, mô hình STI với 0 byte NULL và hàm Submodular Knapsack. | $\implies$ **Chứng minh 22 trường dùng chung trong 1 bảng là tối ưu tuyệt đối về I/O và bộ nhớ.** |
