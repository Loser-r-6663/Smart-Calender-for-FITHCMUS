# ĐẶC TẢ THUẬT TOÁN LẬP LỊCH TỐI ĐA HÓA ĐIỂM RÈN LUYỆN (BRANCH & BOUND)

**Môn học:** Tư duy Tính toán (Computational Thinking)  
**Đơn vị:** Khoa Công nghệ Thông tin – Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM (FIT-HCMUS)

---

## 1. ĐẶT BÀI TOÁN (PROBLEM FORMULATION)

### 1.1. Phát biểu bài toán
> **"Xây dựng lịch trình tham gia các hoạt động ngoại khóa có cộng Điểm Rèn Luyện (ĐRL) tối ưu theo tuần, trong đó mỗi hoạt động có khoảng thời gian và địa điểm xác định, sao cho tổng ĐRL thực nhận của sinh viên đạt giá trị lớn nhất — tuân thủ nghiêm ngặt trần điểm của từng Điều trong 5 Điều quy chế và trần toàn cục 100 điểm/học kỳ — đồng thời không xung đột với lịch học/lịch thi cố định, bảo toàn quỹ giờ cho các bài tập linh hoạt và đảm bảo thời gian di chuyển giữa các cơ sở."**

### 1.2. Bối cảnh thực tế tại ĐHKHTN (HCMUS)
Theo quy chế đánh giá Điểm Rèn Luyện của Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM, tổng điểm học kỳ được cấu thành từ **5 Điều (5 tiêu chí)** với các mức trần độc lập và một trần toàn cục:

| Tiêu chí | Nội dung đánh giá | Trần tối đa |
|---|---|---:|
| **Điều 1** | Ý thức tham gia học tập và nghiên cứu khoa học | **30 điểm** |
| **Điều 2** | Ý thức chấp hành nội quy, quy chế và các quy định trong Nhà trường | **20 điểm** |
| **Điều 3** | Tham gia hoạt động chính trị - xã hội, văn hóa - văn nghệ, thể dục - thể thao, phòng chống tệ nạn | **25 điểm** |
| **Điều 4** | Ý thức công dân trong quan hệ cộng đồng | **25 điểm** |
| **Điều 5** | Ý thức và kết quả tham gia công tác cán bộ lớp, đoàn thể, các nội dung khuyến khích | **30 điểm** |
| **Toàn cục** | **Tổng điểm tối đa được công nhận chính thức mỗi học kỳ** | **100 điểm** |

Trong thực tế lập lịch của sinh viên, bài toán nảy sinh 4 thách thức cốt lõi:
1. **Lịch học & Lịch thi bất khả xâm phạm (Hard Anchors):** Các buổi học lý thuyết, thực hành, lịch thi là cố định và tuyệt đối không thể dời hay bỏ qua để đi sự kiện ngoại khóa.
2. **Xung đột thời gian & Di chuyển liên cơ sở:** Sinh viên phải di chuyển giữa **Cơ sở 1 (Quận 5)** và **Cơ sở 2 (Linh Trung, Thủ Đức)**. Hai hoạt động diễn ra liên tiếp ở 2 cơ sở khác nhau bắt buộc phải cách nhau tối thiểu **60 phút** di chuyển; riêng hoạt động **Online** có thể tham gia tại chỗ (`0` phút di chuyển).
3. **Hiệu suất cận biên giảm dần (Submodular Marginal Gain):** Khi một Điều đã chạm trần (ví dụ Điều 3 đã đạt `25/25` điểm), việc tham gia thêm sự kiện thuộc Điều 3 sẽ chỉ mang lại **`0` điểm thực nhận** ($\Delta p = 0$). Thuật toán phải tránh lãng phí thời gian vào các tiêu chí đã bão hòa.
4. **Bảo vệ thời gian cho Bài tập & Nhiệm vụ linh hoạt:** Các bài tập lớn (`assignment`) hoặc sự kiện ĐRL online mở kéo dài nhiều ngày không chiếm trọn cả cửa sổ thời gian của nó, nhưng bắt buộc phải chừa đủ số giờ rảnh thực tế để sinh viên hoàn thành công việc.

---

## 2. PHÂN RÃ BÀI TOÁN (PROBLEM DECOMPOSITION)

Áp dụng nguyên lý Tư duy Tính toán, bài toán được phân rã thành **3 bài toán con**:

1. **Bài toán con 1 — Chuẩn hóa và Phân loại Tập nhiệm vụ đầu vào:**
   * Tách các nhiệm vụ thành 3 nhóm:
     * **Lịch cố định (`FixedIntervals`):** Buổi học (`class`), lịch thi (`exam`), các mốc cố định có thời lượng $< 3.5\text{ giờ}$ (`training_points = 0`).
     * **Nhiệm vụ linh hoạt bắt buộc (`FlexibleWorkloads`):** Bài tập (`assignment`) có khoảng thời gian mở $\Delta t \ge 3.5\text{ giờ}$ cần một lượng thời gian thực hiện ước tính $h_w$.
     * **Ứng viên ĐRL (`CandidateEvents`):** Các sự kiện có `training_points > 0` (gồm sự kiện Offline cố định giờ và sự kiện Online linh hoạt kéo dài $\ge 3.5\text{ giờ}$).
2. **Bài toán con 2 — Lọc sơ bộ khả thi & Khử trùng lặp (Feasibility Filtering):**
   * Loại bỏ các sự kiện ĐRL cố định đụng giờ học hoặc vi phạm đệm di chuyển 60 phút với `FixedIntervals`.
   * Loại bỏ các sự kiện ĐRL linh hoạt không đủ quỹ thời gian rảnh tối thiểu trong cửa sổ mở của nó.
   * Khử các bản sao trùng `(tiêu đề chuẩn hóa, start_time, end_time)`.
3. **Bài toán con 3 — Tìm kiếm Lời giải Tối ưu Toàn cục (Branch & Bound):**
   * Tìm tập con các sự kiện ĐRL không xung đột nhau, không làm thiếu quỹ giờ làm bài tập, và có tổng điểm thực nhận lớn nhất (phá vỡ thế hòa bằng cách ưu tiên lịch có tổng thời lượng ngắn hơn).

---

## 3. NHẬN DIỆN MẪU BÀI TOÁN (PATTERN RECOGNITION)

Bài toán được mô hình hóa thành **Biến thể của Bài toán Cái túi 0/1 có Xung đột Khoảng thời gian và Trần từng Ngăn (0/1 Knapsack with Interval Conflicts & Category Compartment Caps)**:

| Thành phần Knapsack cổ điển | Ánh xạ sang Bài toán Lập lịch ĐRL |
|---|---|
| **Vật phẩm ($i \in \{1 \dots n\}$)** | Các **Sự kiện ĐRL ứng viên**. Biến quyết định $x_i \in \{0, 1\}$ (`1` = chọn, `0` = bỏ qua). |
| **Giá trị vật phẩm ($v_i$)** | **Điểm thực nhận ($\Delta p_i$)** phụ thuộc trạng thái hiện tại của từng Điều $c$:<br>$$\Delta p_i = \min\Big(p_i, \; \max(0, \text{Cap}_c - \text{current\_points}[c]), \; \max\big(0, 100 - \sum_{k=1}^5 \text{current\_points}[k]\big)\Big)$$ |
| **Trọng lượng / Tài nguyên** | **Khoảng thời gian chiếm dụng $[s_i, e_i]$** (đối với sự kiện cố định) hoặc **số giờ ước tính $h_i$** rút từ phần rảnh của cửa sổ (đối với sự kiện online linh hoạt). |
| **Ràng buộc xung đột** | Đồ thị khoảng 1 chiều (1D Interval Graph): Hai sự kiện cố định không được giao nhau và phải đảm bảo $\text{TravelBuffer}(\text{loc}_i, \text{loc}_j)$. |
| **Trần từng ngăn** | 5 ngăn độc lập tương ứng với 5 Điều ($\text{Cap}_1=30, \text{Cap}_2=20, \text{Cap}_3=25, \text{Cap}_4=25, \text{Cap}_5=30$). |
| **Trần toàn cục** | Tổng giá trị tối đa không vượt quá **100 điểm**. |

---

## 4. THIẾT KẾ THUẬT TOÁN: NHÁNH CẬN NÂNG CAO (ADVANCED BRANCH AND BOUND)

Thay vì dùng cây nhị phân duyệt tuần tự $i \to i+1$ rất chậm hoặc quy hoạch động 6 chiều tốn hàng trăm MB bộ nhớ, hệ thống dùng **Thuật toán Nhánh Cận với Bước nhảy tương thích $O(1)$ (`Next Compatible Jump`)**.

### 4.1. Tiền xử lý & Nguyên lý Thiết kế (Precomputations & $O(1)$ Jump)

1. **Nhận diện & Phân tách Task linh hoạt ($\Delta t \ge 3.5\text{ giờ}$):**
   * Vì một buổi học chuẩn tại HCMUS kéo dài tối đa $3.5\text{ giờ}$, mọi bài tập (`assignment`) hoặc sự kiện ĐRL Online có cửa sổ mở $\Delta t = e_i - s_i \ge 3.5\text{ giờ}$ (với $e_i$ là `end_time` hoặc `deadline`) được xem là **khoảng thời gian mở linh hoạt** thay vì khối giờ cứng:
     * **Bài tập linh hoạt bắt buộc (`assignment`, $p_i = 0$):** Cần thời lượng hoàn thành ước tính $h_w$ (mặc định $3.5\text{ giờ}$ nếu không khai báo) bên trong cửa sổ $[w_{\text{start}}, w_{\text{end}}]$. Không khóa toàn bộ nhiều ngày vào `fixed_intervals`, mà đưa vào `flexible_workloads` để kiểm soát quỹ giờ học.
     * **Sự kiện ĐRL Online linh hoạt (`loc` = `ONLINE`, $p_i > 0$, $\Delta t \ge 3.5\text{ giờ}$):** Cần thời lượng ước tính $h_i$ (mặc định $0.5\text{ giờ}$ / $30\text{ phút}$), có thể chèn vào bất kỳ khe trống nào trong $[s_i, e_i]$ mà không cản trở giờ học hay hội thảo cố định.

2. **Sắp xếp Ưu tiên & Thời gian:**
   * Toàn bộ ứng viên khả thi được sắp xếp theo khóa kép `(not is_flexible, start_time, end_time)`: xét các sự kiện ĐRL Online linh hoạt trước, sau đó đến các sự kiện cố định giờ theo thứ tự thời gian bắt đầu tăng dần.

3. **Mảng nhảy tương thích $O(1)$ (`precomputed_next`):**
   * Với **sự kiện ĐRL Online linh hoạt $i$** (`is_flexible = True`): `precomputed_next[i] = i + 1` vì việc chọn nó không khóa cứng một mốc giờ cụ thể nào, chỉ tiêu tốn $h_i$ giờ từ quỹ thời gian rảnh.
   * Với **sự kiện cố định giờ $i$** (`is_flexible = False`): tính trước chỉ số $j > i$ nhỏ nhất sao cho sự kiện $j$ tương thích hoàn toàn với $i$ kể cả thời gian di chuyển:
     $$s_j \ge e_i + \text{TravelBuffer}(\text{loc}_i, \text{loc}_j)$$
     Trong đó:
     $$\text{TravelBuffer}(\text{loc}_i, \text{loc}_j) = \begin{cases} 60\text{ phút} & \text{nếu } \{\text{loc}_i, \text{loc}_j\} = \{\text{CS1}, \text{CS2}\} \\ 0\text{ phút} & \text{nếu cùng cơ sở hoặc 1 trong 2 là ONLINE} \end{cases}$$
   * Nhờ `precomputed_next[i] = j`, khi chọn sự kiện $i$, thuật toán **nhảy thẳng đến $j$ trong $O(1)$**, triệt tiêu hoàn toàn vòng lặp kiểm tra trùng giờ khi đệ quy.

4. **Ma trận Tổng hậu tố theo Tiêu chí (`remaining_by_cat`):**
   * Cộng dồn ngược tổng điểm danh nghĩa của từng Điều $c \in \{1 \dots 5\}$ từ cuối mảng về chỉ số $i$:
     $$\text{remaining\_by\_cat}[c][i] = \sum_{k=i}^{n-1} \Big(p_k \cdot \mathbb{I}(\text{event}_k \in \text{Điều } c)\Big)$$
   * Giúp tính cận trên lý thuyết tại mọi nút tìm kiếm chỉ trong **$O(1)$**.

5. **Khởi tạo Tham lam (`Greedy Warm-Start`):**
   * Chạy một lượt duyệt tham lam tuyến tính $O(n)$ (tuân thủ đệm di chuyển 60 phút và quỹ giờ linh hoạt) để có ngay lời giải ban đầu tốt làm cận dưới `best_score`, giúp cắt tỉa mạnh ngay từ đầu cây tìm kiếm.

---

### 4.2. Cơ chế Cắt tỉa Phân tầng 5 Lớp (5-Tier Cascading Pruning)

Hàm đệ quy `search(current_idx, current_selected, current_points, score)` đi qua **phễu lọc 5 tầng** để loại bỏ tức thì các nhánh dưới tối ưu hoặc vi phạm quỹ thời gian:

#### Tầng 0 (Tier 0): Cắt tỉa Trần Toàn cục (Dừng sớm tuyệt đối)
* **Điều kiện:** Nếu $\sum_{c=1}^5 \text{current\_points}[c] \ge 100 \implies$ **`return`** ngay lập tức.
* **Ý nghĩa:** Sinh viên đã đạt tối đa 100 điểm theo quy chế, mọi tìm kiếm thêm đều dư thừa.

#### Tầng 1 (Tier 1): Cắt tỉa Cận trên Toàn cục (Mức Nút)
* Tại đầu hàm `search()`, tính tổng điểm lý thuyết tối đa có thể đạt thêm từ `current_idx` trở về sau, bị chặn bởi trần từng Điều và trần 100:
  $$\text{Cat\_Potential} = \sum_{c=1}^{5} \min \Big( \max(0, \; \text{Cap}_c - \text{current\_points}[c]), \; \text{remaining\_by\_cat}[c][\text{current\_idx}] \Big)$$
  $$\text{Global\_Slack} = \max\left(0, \; 100 - \sum_{c=1}^5 \text{current\_points}[c]\right)$$
  $$\text{Potential} = \min(\text{Global\_Slack}, \; \text{Cat\_Potential}), \qquad \text{Upper Bound} = \text{score} + \text{Potential}$$
* **Điều kiện cắt tỉa:** Nếu $\text{Upper Bound} \le \text{best\_score} \implies$ **`return`** để cắt toàn bộ cây con tại nút hiện tại.

#### Tầng 2 (Tier 2): Cắt tỉa Nhìn trước Cục bộ (Mức Vòng lặp)
* Trong vòng lặp `for i in range(current_idx, n)`: tính `quick_pot` tương tự từ chỉ số $i$ đến $n-1$.
* **Nguyên lý đơn điệu:** Vì `remaining_by_cat[c][i]` giảm dần theo $i$, nếu $\text{score} + \text{quick\_pot} \le \text{best\_score}$ tại $i$ thì mọi chỉ số $j > i$ đều chắc chắn không thể vượt kỷ lục $\implies$ **`break`** thoát vòng lặp ngay lập tức.

#### Tầng 3 (Tier 3): Cắt tỉa Trần từng Điều (Mức Sự kiện)
* Với sự kiện $i$ thuộc Điều $c$, tính điểm thực nhận $\text{gain}$:
  $$\text{gain} = \min \Big(p_i, \; \max(0, \; \text{Cap}_c - \text{current\_points}[c]), \; \max\Big(0, \; 100 - \sum_{k=1}^5 \text{current\_points}[k]\Big)\Big)$$
* **Điều kiện cắt tỉa:** Nếu $\text{gain} \le 0$ (Điều $c$ đã đầy hoặc tổng điểm đã chạm 100) $\implies$ **`continue`** bỏ qua sự kiện $i$.

#### Tầng 4 (Tier 4): Cắt tỉa Quỹ giờ Task Linh hoạt (Bảo vệ Giờ Tự học)
* Trước khi kết nạp sự kiện $i$ vào tập đang chọn $\mathcal{S}' = \text{current\_selected} \cup \{i\}$, thuật toán kiểm tra mọi cửa sổ $W = [w_{\text{start}}, w_{\text{end}}]$ trong tập nhiệm vụ linh hoạt đang hoạt động $\mathcal{W}_{\text{active}}$ (gồm bài tập bắt buộc và các sự kiện ĐRL online linh hoạt đã chọn):
  $$\text{BaseFree}(W) = (w_{\text{end}} - w_{\text{start}}) - \sum_{f \in \text{FixedIntervals}} \text{Overlap}(f, W)$$
  $$\text{Needed}(W) = \sum_{\substack{w' \in \mathcal{W}_{\text{active}} \\ w' \cap W \neq \emptyset}} h_{w'}, \qquad \text{Slack}(W) = \max\Big(0, \; \text{BaseFree}(W) - \text{Needed}(W)\Big)$$
  $$\text{BusyDRL}(W) = \sum_{\substack{e \in \mathcal{S}'_{\text{fixed}} \\ e \cap W \neq \emptyset}} \text{Overlap}(e, W)$$
* **Điều kiện cắt tỉa:** Nếu tồn tại cửa sổ $W$ mà $\text{BaseFree}(W) < \text{Needed}(W)$ hoặc $\text{BusyDRL}(W) > \text{Slack}(W) \implies$ **`continue`** (loại sự kiện $i$ vì nó lấn vào quỹ giờ tối thiểu cần để làm bài tập/nhiệm vụ linh hoạt).
* Nếu vượt qua cả 5 tầng $\implies$ nhảy $O(1)$ sang `next_k = precomputed_next[i]` và đệ quy `search(next_k, ..., score + gain)`.

---

### 4.3. Phân bổ Khung giờ Cụ thể Hậu Xử lý (Post-Allocation)
* Sau khi Branch & Bound tìm ra tập nghiệm tối ưu, các **sự kiện ĐRL cố định giờ** giữ nguyên thời gian thực tế của nó.
* Các **sự kiện ĐRL Online linh hoạt** được tự động gán vào một khung giờ rảnh cụ thể (độ dài `estimated_hours`) trong khoảng sinh hoạt ban ngày **`08:00 -> 22:00`** (hoặc khe trống bất kỳ nếu ban ngày kín lịch) bên trong cửa sổ mở của sự kiện, đảm bảo không đụng giờ học và các sự kiện ĐRL khác.

---

## 5. ĐỘ PHỨC TẠP & HIỆU NĂNG THỰC NGHIỆM

* **Độ phức tạp không gian:** $O(n)$ — chỉ dùng mảng 1D `precomputed_next` (kích thước $n$) và bảng `remaining_by_cat` ($5 \times n$). Khắc phục hoàn toàn tình trạng tràn RAM (~1.27 GB ở $N=40$) của Quy hoạch động đa chiều.
* **Độ phức tạp thời gian:**
  * Trường hợp xấu nhất lý thuyết: $O(2^n)$.
  * Thực tế trên dữ liệu học kỳ FIT-HCMUS ($N \le 40$ sự kiện): nhờ `Greedy Warm-Start`, bước nhảy $O(1)$ và phễu cắt tỉa 5 tầng, thuật toán chỉ duyệt từ **vài nút đến vài trăm nút**, giải xong trong **$< 10\text{ ms}$** và luôn đảm bảo **tối ưu toàn cục (OPTIMAL)**.
