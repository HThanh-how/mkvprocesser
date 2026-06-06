# mkvtools — Tài liệu Thiết kế UI/UX (bàn giao Designer)

> **Đây là tài liệu THIẾT KẾ UI/UX** — tập trung vào *bố cục, hệ thống thị giác,
> component, trạng thái, tương tác, responsive, microcopy*. KHÔNG phải system
> design (không API/DB/kiến trúc — cái đó nằm ở `UI_UX_SPEC.md`).
>
> Mục tiêu: designer đọc xong dựng được **wireframe → hi-fi → prototype** trong
> Figma. Bố cục mô tả ở mức wireframe chi tiết; designer tự nâng thành hi-fi.

---

## 0. Tóm tắt sản phẩm (1 câu)
Công cụ web: **dán link phim → tự tải → tách audio → đăng YouTube → dọn ổ**, có
**đăng nhập/phân quyền** và chế độ **"Bắt tay"** (điều khiển trình duyệt từ xa để
bắt link khó). Người dùng chính: chủ kho phim, thao tác hằng ngày, cần *theo dõi
hàng đợi rõ ràng* và *thao tác tối thiểu*.

## 1. Nguyên tắc thiết kế (Design Principles)
1. **Dán-rồi-quên.** Hành động chính (dán link) phải nổi bật nhất màn hình; mọi
   thứ khác là phụ.
2. **Trạng thái luôn rõ.** Mỗi việc đang ở đâu (tải %/tách/đăng) phải thấy tức thì,
   không cần đoán.
3. **Tối giản nhưng có nhịp.** Nền tối, ít màu; màu chỉ dùng cho *trạng thái* và
   *hành động*.
4. **Tha thứ lỗi.** Lỗi 1 link không được làm hoảng; luôn có "Thử lại".
5. **Một tay dùng được.** Luồng chính bấm ≤ 2 lần.

## 2. Personas & Jobs-to-be-done
- **Chủ kho (Admin)** — "Tôi có link/phim, muốn nó tự lên YouTube và không đầy ổ."
  Cần: dán hàng loạt, theo dõi, xử lý link khó.
- **Thành viên (User)** — "Tôi chỉ thêm link, xem nó chạy." Không thấy phần quản trị.
- **Người vận hành** — thỉnh thoảng vào sửa cấu hình, xem lỗi.

## 3. Kiến trúc thông tin & Điều hướng (IA)
```
Đăng nhập
└── (đã đăng nhập) App shell: Sidebar trái + Topbar
    ├── Hàng đợi (Dashboard)        ← mặc định
    ├── Bắt tay (Manual catch)
    ├── Lịch sử
    ├── Quản trị tài khoản          ← chỉ Admin
    └── Cài đặt                      ← chỉ Admin
```
**Điều hướng:** Sidebar trái cố định (desktop) gom 5 mục + khối user ở đáy. Topbar
mỏng hiển thị tiêu đề trang + hành động nhanh + chuông thông báo. Mobile: sidebar
thu thành bottom-tab hoặc hamburger.

---

## 4. Design System (Design Tokens)

### 4.1 Màu (dark-first)
| Vai trò | Token | Hex |
|---|---|---|
| Nền nền | `bg/base` | `#0F1115` |
| Bề mặt (card) | `surface/1` | `#1A1D24` |
| Bề mặt nổi (hover/raised) | `surface/2` | `#21252E` |
| Viền | `border` | `#2A2F3A` |
| Chữ chính | `text/hi` | `#E8EAED` |
| Chữ phụ | `text/mute` | `#9AA0AA` |
| Hành động (Primary) | `accent` / hover | `#3B82F6` / `#2F6FE0` |
| Bắt tay (nhấn riêng) | `accent2` | `#8B5CF6` |
| Thành công | `success` | `#22C55E` |
| Cảnh báo | `warning` | `#F59E0B` |
| Lỗi | `danger` / hover | `#EF4444` / `#DC2626` |
| Thông tin | `info` | `#38BDF8` |
> Nên thiết kế **cả light theme** (đảo `bg`/`surface`/`text`); giữ accent/semantic.
> Đảm bảo tương phản AA: chữ phụ trên nền ≥ 4.5:1.

### 4.2 Typography
- Font: **Inter** (fallback `system-ui`). Mono cho log/URL: **JetBrains Mono**.
- Scale (size/line/weight):
  `Display 30/36/700` · `H1 24/32/700` · `H2 20/28/600` · `Body 15/22/400` ·
  `Body-strong 15/22/600` · `Small 13/18/400` · `Caption 12/16/500` · `Mono 13/20`.

### 4.3 Lưới & khoảng cách
- Base **8px** (cho phép 4px nửa bước). Thang spacing: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`.
- Content tối đa **1200px**; lề trang 24px (desktop), 16px (mobile).
- Lưới 12 cột, gutter 24px.

### 4.4 Bo góc · Đổ bóng · Chuyển động
- Radius: `sm 8` (input/nút), `md 12` (card), `pill 999` (badge/avatar).
- Shadow: card `0 1px 2px rgba(0,0,0,.3)`; popover/menu `0 8px 24px rgba(0,0,0,.45)`.
- Motion: 150ms (hover), 200–250ms (panel/drawer), easing `cubic-bezier(.2,.8,.2,1)`.
  Progress bar chuyển mượt; tránh nhấp nháy.

### 4.5 Icon
Bộ tuyến (Lucide/Feather), 20px trong nút, 16px trong badge. Icon gợi ý: link,
download, scissors (tách), upload, trash (rotation), play, lock, users, settings,
clock (lịch sử), globe (Bắt tay).

---

## 5. Thư viện Component (kèm trạng thái)

| Component | Biến thể | Trạng thái cần vẽ |
|---|---|---|
| **Button** | primary · secondary · ghost · danger · icon | default/hover/active/focus/disabled/loading |
| **Text input / Textarea** | mặc định · có icon · có lỗi | empty/focus/filled/error/disabled |
| **Select / Dropdown** | đơn | đóng/mở/chọn/disabled |
| **Toggle / Checkbox** | — | on/off/focus/disabled |
| **Card** | tĩnh · có hành động | mặc định/hover |
| **Status badge (pill)** | đang chờ·đang tải·đang tách·đang đăng·xong·lỗi·bỏ qua | mỗi trạng thái 1 màu (xem §5.1) |
| **Progress bar** | xác định % · vô định (indeterminate) | 0–100% + nhãn tốc độ |
| **Job card** (cốt lõi) | — | xem §6.2 |
| **Table row** (tài khoản) | — | default/hover/selected |
| **Toast** | success/error/info | xuất hiện/tự ẩn |
| **Modal / Drawer** | xác nhận · form | mở/đóng |
| **Tabs / Segmented** | — | active/inactive |
| **Empty state** | — | minh hoạ + CTA |
| **Log console** | — | dòng info/cảnh báo/lỗi (màu khác nhau), auto-scroll |
| **Tooltip** | — | hover/focus |
| **Avatar + menu user** | — | đóng/mở |

### 5.1 Bảng màu Status badge
`Đang chờ` xám `#9AA0AA` · `Đang tải` xanh dương `#38BDF8` · `Đang tách` tím `#8B5CF6`
· `Đang đăng` xanh dương đậm `#3B82F6` · `Xong` xanh lá `#22C55E` · `Lỗi` đỏ `#EF4444`
· `Bỏ qua (trùng)` vàng `#F59E0B`. Mỗi badge = chấm tròn + chữ.

---

## 6. Bố cục từng màn (Wireframe chi tiết)

### App shell (khung chung mọi màn sau đăng nhập)
```
┌───────────┬──────────────────────────────────────────────────────────┐
│  ▣ mkvtools│  Tiêu đề trang                       [🔔]  [● đĩa 171GB]   │ ← Topbar 56px
│           ├──────────────────────────────────────────────────────────┤
│ ▤ Hàng đợi │                                                          │
│ 🌐 Bắt tay │                  NỘI DUNG TRANG                          │
│ ⏱ Lịch sử │                  (max-width 1200, lề 24)                  │
│ 👥 Tài khoản│                                                          │
│ ⚙ Cài đặt  │                                                          │
│           │                                                          │
│ ───────── │                                                          │
│ 👤 admin ▾ │                                                          │ ← khối user đáy sidebar
└───────────┴──────────────────────────────────────────────────────────┘
   Sidebar 240px (thu còn 64px icon-only khi hẹp)
```
- Mục sidebar đang chọn: nền `surface/2` + thanh accent trái 3px.
- "Tài khoản"/"Cài đặt" chỉ hiện với Admin.

---

### 6.1 Màn ĐĂNG NHẬP
```
                     ▣ mkvtools
        ┌────────────────────────────────────┐
        │  Đăng nhập                          │  H2
        │  ┌──────────────────────────────┐  │
        │  │ Tên đăng nhập                │  │  input
        │  └──────────────────────────────┘  │
        │  ┌──────────────────────────────┐  │
        │  │ Mật khẩu                 [👁] │  │  input + nút hiện mật khẩu
        │  └──────────────────────────────┘  │
        │  [ ⟶  Đăng nhập ]  (full width)    │  primary, loading khi gửi
        │  ⚠ Sai tài khoản hoặc mật khẩu     │  chỉ hiện khi lỗi (đỏ)
        └────────────────────────────────────┘
```
- Card 360–400px, căn giữa, logo phía trên. Nền có thể thêm gradient nhẹ.
- **States:** mặc định · focus từng ô · đang gửi (nút loading) · lỗi (viền ô đỏ +
  dòng cảnh báo) · disabled khi trống.

---

### 6.2 Màn HÀNG ĐỢI (Dashboard) — màn quan trọng nhất
```
Hàng đợi                                          [🔔]  [● đĩa 171GB trống]
┌──────────────────────────────────────────────────────────────────────┐
│  Dán link để bắt đầu                                                  │ ← KHỐI ACTION (nổi bật)
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Mỗi dòng 1 link (YouTube · trang phim · Google Drive · .mkv)    │  │ textarea 3–5 dòng
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  [ + Thêm vào hàng đợi ]   ⚙ upload: Bật · xoá nguồn sau khi đăng     │ primary + chú thích
└──────────────────────────────────────────────────────────────────────┘

┌── Thống kê nhanh (4 thẻ nhỏ) ────────────────────────────────────────┐
│ [▶ Đang chạy: 1] [⏳ Chờ: 3] [✓ Hôm nay: 12] [💾 Ổ: 171GB] │
└──────────────────────────────────────────────────────────────────────┘

Đang xử lý
┌──────────────────────────────────────────────────────────────────────┐
│ 🎬 Mercy 2026 2160p …                              ● Đang đăng        │ ← JOB CARD
│    ███████████████████░░░░░  78%   ↑ 12.4 MB/s · 2/2 audio            │   progress + chi tiết
│    FHD·VIE  FHD·ENG                              [⏸]  [✕ Huỷ]         │   badges + actions
└──────────────────────────────────────────────────────────────────────┘

Hàng chờ (3)                                                  [Xoá hết]
┌──────────────────────────────────────────────────────────────────────┐
│ ⏳ https://…/phim-2.mkv                          ⋮  [↑][↓][✕]          │
│ ⏳ https://youtube.com/watch?v=…                  ⋮  [↑][↓][✕]          │
└──────────────────────────────────────────────────────────────────────┘

Gần đây (Lịch sử rút gọn)                                  [Xem tất cả →]
┌──────────────────────────────────────────────────────────────────────┐
│ ✓ Phim A (4K_VIE) · 2 video · 3 phút trước        [Mở YouTube ↗]      │
│ ✗ Phim B · lỗi: tải 404                            [Thử lại ↻]        │
│ ⊘ Phim C · bỏ qua (đã có theo tựa)                                    │
└──────────────────────────────────────────────────────────────────────┘

▾ Nhật ký trực tiếp (mở/đóng) — log console mono, auto-scroll
```
**Đặc tả Job Card (component cốt lõi — cần hi-fi kỹ):**
- Trái: icon/thumbnail loại (phim 🎬 / nhạc / file). 
- Dòng 1: tên (cắt … nếu dài) + **status badge** bên phải.
- Dòng 2: **progress bar** (đổi nhãn theo pha: "Đang tải 78% · 12 MB/s" → "Đang tách
  2/2" → "Đang đăng video 1/2") + các **badge bản audio** (FHD·VIE…).
- Dòng 3 / hover: hành động `Tạm dừng · Huỷ · Thử lại · Mở YouTube`.
- Lỗi → card viền đỏ nhạt + lý do + nút **Thử lại** nổi.
- Trùng → badge vàng "Bỏ qua".

**States của màn:** 
- *Rỗng* (chưa có việc): textarea + empty-state minh hoạ "Dán link đầu tiên".
- *Đang chạy*: có job card progress.
- *Lỗi*: card đỏ + toast.
- *Mất kết nối server*: banner "Mất kết nối — đang thử lại…".

---

### 6.3 Màn "BẮT TAY" (Manual catch) — bố cục 2 cột
```
Bắt tay                                                  ● Đang nghe ⦿
┌───────────────────────────────────────────────┬──────────────────────┐
│                                               │  Điều khiển          │
│        KHUNG TRÌNH DUYỆT (noVNC)              │  [▶ Bắt đầu nghe]     │
│        — bạn lái trực tiếp ở đây —            │  [■ Dừng] [⟲ Xoá]    │
│        (16:9, chiếm ~70% bề ngang)            │                      │
│                                               │  Media bắt được (3)  │
│                                               │  ┌────────────────┐  │
│                                               │  │ ▣ master.m3u8  │  │ ← item
│                                               │  │ 1080p·HLS      │  │
│                                               │  │ [+ Hàng đợi]   │  │
│                                               │  ├────────────────┤  │
│                                               │  │ ▣ video.mp4    │  │
│                                               │  │ [+ Hàng đợi]   │  │
│                                               │  └────────────────┘  │
└───────────────────────────────────────────────┴──────────────────────┘
 Hướng dẫn 3 bước (banner mỏng dưới): 1 Mở trang · 2 Phát video · 3 Bấm "+ Hàng đợi"
```
- Cột trái: iframe trình duyệt (tỉ lệ giữ 16:9, có khung + nhãn "Bạn đang điều khiển").
- Cột phải: trạng thái nghe (chấm pulse khi đang nghe) + nút điều khiển + **danh sách
  media** (mỗi item: tên rút gọn, badge loại/chất lượng, nút "+ Hàng đợi"; bấm xong
  đổi thành "✓ đã thêm").
- **States:** chưa nghe (CTA "Bắt đầu nghe") · đang nghe (danh sách trống → hint
  "phát video đi") · có media · lỗi kết nối khung.
- Mobile: xếp dọc (khung trên, danh sách dưới).

---

### 6.4 Màn LỊCH SỬ
```
Lịch sử            [🔎 tìm tên]   [Lọc: Tất cả ▾]   [Khoảng ngày ▾]
┌──────────────────────────────────────────────────────────────────────┐
│ Trạng thái │ Tên               │ Bản     │ Thời gian   │ Hành động     │
│ ✓ Xong     │ Mercy 2026 (4K)   │ VIE,ENG │ 13:42       │ [YouTube ↗]   │
│ ✗ Lỗi      │ Phim B            │ —       │ 13:30       │ [Thử lại ↻]   │
│ ⊘ Bỏ qua   │ Phim C            │ —       │ 12:10       │ [Chi tiết]    │
└──────────────────────────────────────────────────────────────────────┘
```
- Bảng (desktop) / list card (mobile). Hàng bấm được → drawer chi tiết (log của job đó).
- States: rỗng · đang tải · có dữ liệu · không khớp tìm kiếm.

---

### 6.5 Màn QUẢN TRỊ TÀI KHOẢN (Admin)
```
Quản trị tài khoản                                   [+ Thêm tài khoản]
┌──────────────────────────────────────────────────────────────────────┐
│ Người dùng      │ Vai trò │ Trạng thái │ Hành động                    │
│ 👤 admin (bạn)  │ ●Admin  │ Hoạt động  │ — (không tự sửa mình)        │
│ 👤 bob          │ ○User   │ Hoạt động  │ [→Admin] [Khoá] [Đổi MK] [🗑] │
│ 👤 carol        │ ○User   │ 🔒Khoá     │ [Mở khoá] [Đổi MK] [🗑]       │
└──────────────────────────────────────────────────────────────────────┘
```
- "Thêm tài khoản" + "Đổi mật khẩu" mở **drawer/modal** (không phải form rời rạc
  như hiện tại): ô tên, mật khẩu (có nút hiện), chọn vai trò, nút Lưu.
- Vai trò = badge (Admin tím / User xám). Hành động lên-chính-mình bị disable + tooltip
  "Không thể tự thao tác".
- Xoá → modal xác nhận "Xoá carol? Không hoàn tác."
- States: 1 tài khoản · nhiều · đang lưu · lỗi trùng tên (inline).

---

### 6.6 Màn CÀI ĐẶT (đề xuất — đưa cấu hình lên UI)
Nhóm thành section + hàng "label · mô tả · control":
- **Đăng tải:** Quyền riêng tư (private/unlisted/public — *gợi ý mặc định private,
  cảnh báo nếu chọn public*), playlist, tiêu đề mẫu (preview trực tiếp).
- **Ổ đĩa / Rotation:** Bật xoá nguồn (toggle), ngưỡng GB trống (slider/number),
  thư mục tải.
- **Bắt link:** cookies.txt (upload file), proxy.
- **Phụ đề & audio:** caption (tất cả/cùng-lang), audio mỗi ngôn ngữ (tốt nhất/tất cả).
- States: lưu tức thì (toast "Đã lưu") hoặc nút "Lưu thay đổi".

---

## 7. Ma trận trạng thái (vẽ đủ cho mỗi màn)
| Màn | Rỗng | Đang tải | Thành công | Lỗi | Ngoại lệ |
|---|---|---|---|---|---|
| Hàng đợi | empty-state "dán link đầu tiên" | skeleton job card | toast + card xanh | card đỏ + Thử lại | mất kết nối → banner |
| Bắt tay | "Bắt đầu nghe" | khung đang tải | media list | khung lỗi/treo | hết phiên → về login |
| Lịch sử | "Chưa có việc nào" | skeleton bảng | bảng | — | tìm không ra |
| Quản trị | (luôn ≥1) | — | toast | trùng tên inline | 403 nếu không phải admin |
| Đăng nhập | — | nút loading | → vào app | viền đỏ + cảnh báo | khoá tài khoản |

> **Bắt buộc thiết kế:** empty state, skeleton/loading, error+retry, toast,
> "phiên hết hạn", "mất kết nối server", disabled/loading cho nút.

## 8. Responsive
- **Desktop ≥1024px:** sidebar 240px + nội dung 12 cột.
- **Tablet 640–1023px:** sidebar thu icon-only (64px); job card full-width.
- **Mobile <640px:** sidebar → bottom-tab (Hàng đợi · Bắt tay · Lịch sử · ⋯);
  textarea + nút full-width; job card 1 cột; Bắt tay xếp dọc; bảng → list card.

## 9. Tương tác & Micro-interaction
- Nút primary: hover sáng nhẹ + nhích 0; active lún 1px; loading = spinner thay chữ.
- Thêm link: textarea xác nhận → item *trượt vào* hàng chờ + toast "Đã thêm N link".
- Progress: cập nhật mượt (không giật); đổi nhãn theo pha; xong → tích xanh + nhói nhẹ.
- "+ Hàng đợi" (Bắt tay): bấm → nút đổi "✓ đã thêm" (200ms) + item mờ đi.
- Log console: dòng mới *fade-in*, auto-scroll, có nút "tạm dừng cuộn".
- Xoá/huỷ: luôn confirm nếu không hoàn tác; còn lại cho **Hoàn tác** qua toast 5s.

## 10. Accessibility
- Tương phản AA (chữ ≥4.5:1, chữ lớn ≥3:1). Đừng chỉ dùng MÀU để báo trạng thái —
  kèm icon + chữ.
- Focus ring rõ (2px accent) trên mọi control; thao tác bàn phím đầy đủ (Tab/Enter/Esc).
- Nhãn ARIA cho icon-button; progress có `aria-valuenow`.
- Tôn trọng `prefers-reduced-motion` (tắt animation mạnh).

## 11. Microcopy / Giọng văn (tiếng Việt, có dấu)
- Ngắn, thân thiện, chủ động. Nút = động từ: "Thêm vào hàng đợi", "Bắt đầu nghe".
- Lỗi nói rõ + lối thoát: *"Tải lỗi (404). Kiểm tra link rồi Thử lại."*
- Trạng thái dùng từ đời thường: "Đang tải · Đang tách · Đang đăng · Xong".
- Tránh thuật ngữ kỹ thuật ở nút (đừng "remux", "CDP"); để trong tooltip nếu cần.
> Hiện code dùng tiếng Việt **không dấu** — bản hi-fi nên chuyển **có dấu** + chuẩn hoá.

## 12. User Flow (hành trình)
**F1 — Thêm link (chính):** Đăng nhập → Hàng đợi → dán link → "Thêm" → xem job card
chạy → xong (toast + Lịch sử). *Cảm xúc cần: yên tâm, thấy tiến trình.*
**F2 — Link khó:** Hàng đợi (link thất bại) → "Thử Bắt tay" → màn Bắt tay → lái +
phát → "+ Hàng đợi" → quay lại theo dõi.
**F3 — Quản trị:** (Admin) Tài khoản → "Thêm tài khoản" (drawer) → cấp cho thành viên.

## 13. Bàn giao mong đợi từ Designer
1. **Figma file** cấu trúc: `Tokens` · `Components` (library) · `Screens` (mỗi màn
   đủ states) · `Prototype` (luồng F1, F2).
2. **Design tokens** xuất được (màu/chữ/spacing) để dev áp.
3. Bộ **2 theme** (tối mặc định + sáng).
4. **Responsive**: desktop + mobile cho ít nhất Hàng đợi & Bắt tay.
5. Spec **Job Card** + **Status badge** + **Bắt tay panel** (3 component đặc thù).

---

### Phụ lục — Bản đồ màn ↔ tính năng (để designer khỏi sót)
Đăng nhập · **Hàng đợi** (dán link, job card, hàng chờ, lịch sử rút gọn, log) ·
**Bắt tay** (khung trình duyệt + media bắt được) · **Lịch sử** (bảng + chi tiết) ·
**Quản trị** (bảng tài khoản + drawer thêm/đổi) · **Cài đặt** (nhóm cấu hình).

*Tham chiếu hiện trạng (ảnh chụp) đính kèm khi bàn giao. Chi tiết kỹ thuật/luồng dữ
liệu: xem `UI_UX_SPEC.md`.*
