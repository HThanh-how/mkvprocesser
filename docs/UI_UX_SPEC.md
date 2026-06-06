# mkvtools — Đặc tả Tính năng & Giao diện (bàn giao UI/UX)

> Tài liệu mô tả TOÀN BỘ tính năng và bố cục giao diện hiện tại của công cụ
> `mkvtools` để đội UI/UX thiết kế lại / chuẩn hoá. Phần "Hiện trạng" mô tả cái
> đang chạy; phần "Cơ hội cải tiến" là gợi ý mở rộng, không bắt buộc.

---

## 1. Sản phẩm là gì

`mkvtools` là công cụ tự động hoá xử lý phim:

1. **Nhận 1 link** (YouTube / trang stream / file-host / link `.mkv .mp4` trực tiếp).
2. **Tự tải** về máy chủ.
3. **Tách** video nhiều audio thành mỗi-ngôn-ngữ-một-file (remux, KHÔNG re-encode → nhanh), rút phụ đề.
4. **Upload** từng bản lên YouTube (chế độ private), kèm phụ đề + playlist.
5. **Xoá nguồn** sau khi upload xong ("xoay vòng đĩa") để ổ nhỏ vẫn xử lý được kho lớn.

Người dùng thao tác qua **web GUI** (server-rendered, chạy trên máy chủ, truy cập bằng trình duyệt). Có **đăng nhập + phân quyền**.

**Triết lý sản phẩm:** dán link → quên đi → hệ thống tự lo. Giao diện nên tối giản, ưu tiên *trạng thái hàng đợi rõ ràng* và *phản hồi tiến trình theo thời gian thực*.

---

## 2. Đối tượng & vai trò

| Vai trò | Quyền |
|---|---|
| **admin** | Mọi thứ + quản trị tài khoản (thêm/khoá/xoá/đổi vai trò/đổi mật khẩu) |
| **user** | Dùng hàng đợi link + xử lý inbox; KHÔNG vào trang Quản trị |
| *(chưa đăng nhập)* | Chỉ thấy màn Đăng nhập |

- Đăng nhập bằng **tên + mật khẩu**; phiên giữ bằng cookie (mặc định 7 ngày).
- Mật khẩu **băm pbkdf2** (không lưu thô).
- Lần đầu hệ thống tự tạo 1 admin.

---

## 3. Ràng buộc kỹ thuật (cho Front-end)

- **Hiện tại:** HTML render từ server (FastAPI), CSS inline tối giản, **theme tối**, khung rộng tối đa ~820px, **cập nhật bằng polling** (tự reload mỗi 2.5s khi có việc chạy).
- **Có sẵn API JSON** để render động (xem §7) → đội FE có thể làm SPA (React/Vue…) gọi API thay vì reload trang.
- Chạy **headless trên máy chủ** (LXC/VPS), không phải app desktop. Truy cập qua LAN/Tailscale.
- Tác vụ **chạy nền nhiều phút** (tải + upload file lớn) → UI phải chịu được trạng thái "đang chạy lâu", mất kết nối, tải lại trang giữa chừng.
- Hiện **chưa responsive mobile** (thiết kế cho desktop).

---

## 4. Danh sách tính năng đầy đủ

### 4.1. Xác thực & tài khoản
- [F1] Đăng nhập (tên + mật khẩu), báo lỗi sai.
- [F2] Đăng xuất.
- [F3] Phiên đăng nhập (cookie, hết hạn tự đăng nhập lại).
- [F4] Phân quyền admin / user; chặn mọi trang nếu chưa đăng nhập.
- [F5] **Quản trị tài khoản** (admin): liệt kê user; thêm; đổi vai trò admin↔user; khoá/mở khoá; xoá; đổi mật khẩu cho bất kỳ user.
- [F6] Chống tự khoá: không thể tự xoá/khoá/hạ quyền chính mình.

### 4.2. Hàng đợi link — luồng tự động (tính năng lõi)
- [F7] Dán **nhiều link cùng lúc** (mỗi dòng 1 link); dòng trống / bắt đầu bằng `#` bị bỏ qua.
- [F8] **Tự tải**: yt-dlp cho YouTube/stream/file-host (kể cả trang "phải bấm nút mới tải"); tải HTTP trực tiếp cho link `.mkv .mp4 …`.
- [F9] **Tự tách** theo từng audio track → mỗi ngôn ngữ 1 file (remux copy, không re-encode).
- [F10] **Rút toàn bộ phụ đề chữ** (text), bỏ phụ đề ảnh (PGS…).
- [F11] **Upload YouTube** từng bản (mặc định private) + tiêu đề có cấu trúc (xem §10).
- [F12] **Upload phụ đề** (caption) cho video.
- [F13] **Playlist**: tự tạo/gộp theo phim.
- [F14] **Xoay vòng đĩa**: xoá file nguồn + bản tạm ngay sau khi upload xong.
- [F15] **Canh đĩa**: chờ đủ X GB trống trước khi tải link kế (tránh tràn ổ).
- [F16] **Xử lý tuần tự** (1 link/lượt) → dung lượng đỉnh bị giới hạn ≈ 1 phim.
- [F17] **Cô lập lỗi**: 1 link lỗi → ghi vào Lịch sử + chạy tiếp link sau (không sập cả hàng).
- [F18] **Trạng thái hàng đợi**: đang chạy, danh sách chờ, lịch sử (xong/lỗi từng link), log trực tiếp.

### 4.3. Chống trùng (thông minh)
- [F19] Bỏ qua file **đã xử lý** (theo chữ ký nội dung — SHA của đầu/cuối file).
- [F20] Bỏ qua phim **trùng tựa** (chuẩn hoá tên, phân biệt Phần 1/2/3).
- [F21] **Nâng cấp độ phân giải**: phim đã có nhưng bản mới nét hơn (vd có 1080p, mới là 2160p) → vẫn upload.

### 4.4. Xử lý file có sẵn (inbox)
- [F22] Liệt kê file trong thư mục inbox.
- [F23] **Phân tích (probe)** 1 file → xem trước kế hoạch: độ phân giải, năm, danh sách audio (ngôn ngữ/kênh/codec), phụ đề — KHÔNG chạy nặng.
- [F24] **Chạy** 1 file (tách + tuỳ chọn upload).

### 4.5. Cấu hình (hiện trong file YAML — gợi ý đưa lên UI dạng trang Cài đặt)
- [F25] Chế độ riêng tư: private / unlisted / public.
- [F26] Phụ đề: caption / ghi đè (burn) / cả hai; up tất cả / chỉ cùng ngôn ngữ.
- [F27] Audio mỗi ngôn ngữ: giữ bản tốt nhất / giữ hết.
- [F28] Định dạng: mp4 / mkv.
- [F29] Mẫu tiêu đề & tên playlist (template có biến).
- [F30] Rotation: bật/tắt xoá nguồn, ngưỡng GB trống.
- [F31] Proxy upload; thư mục tải/làm việc.

---

## 5. Bản đồ màn hình & bố cục (HIỆN TRẠNG)

Có **3 màn**: Đăng nhập · Trang chính · Quản trị. Toàn bộ theme tối, 1 cột, căn giữa.

### 5.1. Màn ĐĂNG NHẬP — `/login` (công khai)

```
                ┌───────────────────────────────┐
                │  Đăng nhập                     │
                │  [ Tên đăng nhập            ]  │
                │  [ Mật khẩu                 ]  │
                │  [        Đăng nhập         ]  │  ← nút full-width
                └───────────────────────────────┘
   (tiêu đề trang: "mkvtools — GUI" ở góc trên trái)
```
- Card căn giữa, ~360px. Sai mật khẩu → hiện dòng đỏ phía trên form.
- **States:** mặc định / báo lỗi (chữ đỏ).

### 5.2. Màn TRANG CHÍNH — `/` (cần đăng nhập)

```
 mkvtools — GUI
                                    admin (admin) · Quản trị · Đăng xuất   ← thanh user (phải)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ Dán link → tự tải → tách → upload → xoay vòng đĩa                     │  ← CARD A (lõi)
 │ ┌──────────────────────────────────────────────────────────────────┐ │
 │ │ (textarea) Mỗi dòng 1 link (YouTube / stream / file-host / .mkv)  │ │
 │ └──────────────────────────────────────────────────────────────────┘ │
 │ [ Thêm vào hàng đợi ]   upload: bật · xoá nguồn sau upload (rotation) │
 │                                                                      │
 │ Đang chạy: (không) · chờ: 0 link                                     │  ← dòng trạng thái
 │ ┌── Hàng chờ ─────────────┐   ┌── Lịch sử ──────────────┐            │  ← 2 cột
 │ │ • link1                 │   │ ✓ phim A   ✗ phim B …   │            │
 │ └─────────────────────────┘   └─────────────────────────┘            │
 │ ┌── Log (cuộn) ────────────────────────────────────────────────────┐ │
 │ │ [tải] … [tách] … [upload id=…] … [xoá nguồn] …                    │ │
 │ └──────────────────────────────────────────────────────────────────┘ │
 └──────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────┐
 │ Hoặc xử lý file có sẵn trong inbox: /data/inbox — 1 file              │  ← CARD B (thủ công)
 │ [ ▼ chọn file ............................ ]  [ Phân tích ]           │
 │ [ ▼ chọn file ............................ ]  ☑ upload YouTube [Chạy] │
 │ ┌── Log ───────────────────────────────────────────────────────────┐ │
 │ └──────────────────────────────────────────────────────────────────┘ │
 └──────────────────────────────────────────────────────────────────────┘
```

**Thành phần CARD A (hàng đợi link):**
| Thành phần | Dữ liệu / hành vi |
|---|---|
| Textarea links | nhập nhiều dòng → POST `/enqueue` |
| Nút "Thêm vào hàng đợi" | đẩy link vào hàng, worker tự chạy |
| Chú thích upload/rotation | đọc từ cấu hình (bật/tắt) |
| "Đang chạy: X · chờ: N" | `current`, độ dài `pending` |
| Cột Hàng chờ | `pending[]` |
| Cột Lịch sử | `history[]` (✓ done / ✗ error + thông báo lỗi) |
| Log | `log[]` (200–300 dòng cuối) |

**Thành phần CARD B (inbox):** dropdown file × 2, nút Phân tích, checkbox upload, nút Chạy, log riêng.

- **Auto-refresh:** trang tự reload mỗi 2.5s khi đang chạy / còn hàng chờ.
- **States mỗi card:** rỗng ("(trống)", "(chưa có)") / đang chạy / có dữ liệu.

### 5.3. Màn QUẢN TRỊ — `/admin` (chỉ admin)

```
                                    admin (admin) · Quản trị · Đăng xuất
 ┌──────────────────────────────────────────────────────────────────────┐
 │ Quản trị tài khoản                                                    │
 │ admin (tôi)   admin · hoạt động   [→ user] [Khoá] [Xoá]               │  ← mỗi user 1 hàng
 │ bob           user  · hoạt động   [→ admin][Khoá] [Xoá]               │     (nút của "tôi" bị mờ)
 └──────────────────────────────────────────────────────────────────────┘
 ┌── Thêm tài khoản ────────────────────────────────────────────────────┐
 │ [ Tên đăng nhập ]  [ Mật khẩu ]  [ ▼ user/admin ]  [ Thêm ]           │
 └──────────────────────────────────────────────────────────────────────┘
 ┌── Đổi mật khẩu ──────────────────────────────────────────────────────┐
 │ [ ▼ chọn user ]  [ Mật khẩu mới ]  [ Đổi ]                            │
 └──────────────────────────────────────────────────────────────────────┘
 « về trang chính
```
- Mỗi hàng user: tên (đánh dấu "(tôi)"), vai trò · trạng thái (hoạt động/khoá), nút đổi-vai-trò, Khoá/Mở khoá, Xoá.
- Nút thao-tác-lên-chính-mình bị **disable** (chống tự khoá).
- Xoá có hộp xác nhận.

---

## 6. Luồng người dùng (User Flows)

**FLOW 1 — Dán link tự động (chính):**
```
Đăng nhập → Trang chính → dán N link vào textarea → "Thêm vào hàng đợi"
→ (nền) tải → tách → upload → xoá nguồn → link kế
→ theo dõi ở Hàng chờ / Lịch sử / Log (tự cập nhật)
```

**FLOW 2 — Xử lý file có sẵn:** Trang chính → Card B → chọn file → "Phân tích" (xem trước) → "Chạy".

**FLOW 3 — Quản trị:** (admin) Trang chính → "Quản trị" → thêm/khoá/đổi vai trò/đổi mật khẩu.

**FLOW 4 — Lần đầu:** hệ thống tạo admin → admin đăng nhập → **đổi mật khẩu** → tạo tài khoản cho thành viên.

---

## 7. API & dữ liệu mỗi màn hình (cho FE render động)

| Method | Endpoint | Công khai? | Mục đích | Trả về |
|---|---|---|---|---|
| GET | `/login` | ✓ | Trang đăng nhập | HTML |
| POST | `/login` | ✓ | Đăng nhập (`username`,`password`) | 302 (+cookie) |
| GET | `/logout` | | Đăng xuất | 302 |
| GET | `/` | login | Trang chính | HTML |
| POST | `/enqueue` | login | Thêm link (`links` nhiều dòng) | 302 |
| **GET** | **`/queue`** | login | **Trạng thái hàng đợi (JSON)** | xem dưới |
| POST | `/analyze` | login | Phân tích 1 file inbox (`file`) | HTML |
| POST | `/run` | login | Chạy 1 file inbox (`file`,`upload?`) | HTML |
| GET | `/status` | login | Trạng thái job inbox (JSON) | `{running, log[]}` |
| GET | `/admin` | admin | Trang quản trị | HTML |
| POST | `/admin/add` | admin | Thêm user (`username`,`password`,`role`) | 302 |
| POST | `/admin/action` | admin | `action`=role/disable/enable/delete/reset (`username`,`value?`) | 302 |

**`GET /queue` JSON** (nguồn chính để vẽ hàng đợi động):
```json
{
  "running": true,
  "current": "https://.../movie.mkv",
  "pending": ["https://link2", "https://link3"],
  "history": [
    { "url": "https://link1", "status": "done",  "name": "Movie.mkv" },
    { "url": "https://linkX", "status": "error", "error": "tải lỗi: 404" }
  ],
  "log": ["[tải] …", "[tách] …", "[upload id=…]", "[xoá nguồn] …"]
}
```
> Gợi ý FE: poll `/queue` mỗi 1–2s (hoặc nâng cấp lên SSE/WebSocket) để cập nhật real-time thay vì reload trang.

---

## 8. Trạng thái & phản hồi cần thiết kế

Mỗi khu vực cần đủ 4 trạng thái:
- **Rỗng:** hàng đợi trống, chưa có lịch sử, chưa có log.
- **Đang chạy:** 1 link đang xử lý (tải/tách/upload) — nên có % tiến trình.
- **Thành công:** link xong (✓) + link YouTube.
- **Lỗi:** link lỗi (✗) + thông báo + cho **thử lại**.

Ngoài ra: đang tải trang, mất kết nối máy chủ, phiên hết hạn (đẩy về `/login`), thao tác quản trị bị từ chối (403).

---

## 9. Cơ hội cải tiến UX (gợi ý — đội design tự quyết)

1. **Thanh tiến trình theo từng link** (tải %, tách %, upload %) thay vì chỉ log chữ.
2. **Hàng đợi dạng thẻ**: mỗi link 1 thẻ có trạng thái màu, nút **Huỷ / Thử lại / Lên-xuống thứ tự**.
3. **Chi tiết mỗi link**: các audio sẽ tách, phụ đề, tiêu đề dự kiến, link YouTube sau khi xong.
4. **Dashboard**: dung lượng ổ còn trống, số phim đã upload, quota YouTube, hàng đợi tổng quan.
5. **Trang Cài đặt** (đưa các mục §4.5 lên UI thay vì sửa file YAML).
6. **Vai trò "viewer"** (chỉ xem, không chạy) — cho người chỉ giám sát.
7. **Responsive mobile** (hiện tối ưu desktop).
8. **Toast/thông báo** khi xong/lỗi; **theme sáng/tối**.
9. **Thực thi real-time** qua WebSocket/SSE thay cho reload 2.5s.
10. **i18n**: hiện 100% tiếng Việt không dấu trong code — nên chuẩn hoá có dấu + đa ngôn ngữ.

---

## 10. Phụ lục

**Quy ước tiêu đề YouTube** (mặc định `{res}_{lang}_{year}_{title}`):
```
FHD_VIE_2011_You Are The Apple Of My Eye
│   │   │    └ tựa đã chuẩn hoá (bỏ rác bản phát hành)
│   │   └ năm
│   └ ngôn ngữ audio (VIE/ENG/CHI…)
└ độ phân giải (4K / FHD / HD / SD)
```
- Nếu thiếu trường (vd không có năm) → tự thu gọn dấu phân cách, không để `__`.
- Cùng 1 ngôn ngữ có nhiều bản → tên file gắn thêm codec (vd `…_dts`, `…_ac3`).

**Thuật ngữ:**
- *Rotation (xoay vòng đĩa):* xoá nguồn ngay sau upload để ổ nhỏ xử lý kho lớn.
- *Remux:* ghép lại luồng video/audio không giải mã lại → nhanh, không giảm chất lượng.
- *Caption:* phụ đề upload kèm video trên YouTube (khác phụ đề ghi-đè vào hình).
- *Idempotency / chống trùng:* nhớ đã xử lý gì để không làm lại / không upload trùng.

---

*Tài liệu sinh kèm mã nguồn. Màn hình tham chiếu: `/login`, `/`, `/admin`. Ảnh chụp hiện trạng đính kèm trong phần bàn giao.*
