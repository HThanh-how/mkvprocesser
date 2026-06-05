# Roadmap — hợp nhất về lõi `mkvtools` (đa nền tảng · thông minh · enterprise)

Tài liệu này là **nguồn sự thật** cho việc di trú. Mục tiêu: một codebase **duy nhất**,
chạy **đa nền tảng**, **thông minh** (giữ phần logic đã chai sạn của app cũ) và **chuẩn
enterprise** (test, CI, container, cấu hình, bảo mật).

## Quyết định kiến trúc

Hai thứ đang tồn tại trong repo:

- **App cũ** `src/mkvprocessor/` + `src/gui/` — desktop PySide6, trói vào Windows
  (PyInstaller `.exe`, `CREATE_NO_WINDOW`, bundle ffmpeg Windows, Git portable). Có phần
  **thông minh thật**: chống xử lý lại bằng chữ ký SHA‑256, chọn track tự động, biết
  RAM/SSD/đĩa, đồng bộ phụ đề lên GitHub.
- **Lõi mới** `src/mkvtools/` — bản viết lại sạch: module nhỏ, hàm thuần có test, chạy
  headless, Docker, CLI `probe/once/watch`, web GUI (FastAPI), upload YouTube. **Đa nền
  tảng từ gốc** nhưng còn **non** (thiếu test tích hợp, watch state nằm RAM, GUI không auth).

**Hướng đi:** lấy **`mkvtools` làm nền**, **port** các phần thông minh của app cũ lên trên,
**gia cố** tới chuẩn enterprise, rồi mới **gỡ** phần Windows‑only. Không phá hủy — app cũ
vẫn chạy được cho tới khi nền mới phủ hết.

## Kiến trúc đích

```
src/mkvtools/
  ffmpeg_helper.py   # dò + gọi ffmpeg/ffprobe (đa nền tảng)            [có]
  metadata.py        # độ phân giải, năm, mã ngôn ngữ (thuần, test)      [có]
  splitter.py        # phân tích track, ghép audio↔sub (thuần, test)     [có]
  uploader.py        # YouTube Data API: upload + caption + playlist     [có]
  pipeline.py        # plan -> split -> upload (dùng chung CLI/GUI/web)  [có]
  cli.py             # probe / once / watch                              [có]
  webui.py           # GUI web FastAPI (fallback làm tay)                [có]
  config.py          # YAML + override env                              [có]
  # --- sẽ port từ app cũ (Phase 3) ---
  idempotency.py     # dedup bằng chữ ký SHA‑256 + log đã xử lý          [ ]
  resources.py       # kiểm tra RAM/SSD/đĩa, chiến lược cache            [ ]
  sync_github.py     # đồng bộ phụ đề/log lên GitHub (opt-in)            [ ]
```

Front-ends: CLI (chính), web GUI (FastAPI), desktop GUI (PySide6 — opt-in `[desktop]`).

## Lộ trình theo giai đoạn

- [x] **Phase 1 — Nền tảng.** Đưa `src/mkvtools/` vào repo. `pyproject.toml` (lõi headless +
  extras `[upload]/[web]/[desktop]/[dev]`), `Dockerfile`, `docker-compose.yml`,
  `config.example.yaml`, test thuần (`tests/test_splitter.py`, 5 pass), CI riêng cho mkvtools
  trên ma trận Linux/Windows/macOS, vệ sinh `.gitignore`. **Không đụng app cũ.**
- [ ] **Phase 2 — Bỏ rác, sạch đa nền tảng.** Gỡ `ffmpeg_bin/` (~190MB .exe Windows) khỏi
  git, chuyển sang tải theo nhu cầu (`tools/download_ffmpeg.py`). (Tùy chọn, cần xác nhận:
  dùng `git filter-repo` xoá khỏi lịch sử — thao tác phá hủy.)
- [ ] **Phase 3 — Port phần "thông minh".** Đưa idempotency (chữ ký SHA‑256), resource-aware
  (RAM/SSD/đĩa), GitHub‑sync (opt-in) lên nền mới dưới dạng module sạch, có test.
- [ ] **Phase 4 — Gia cố enterprise.** Lazy-import để tách extras thật; logging có cấu trúc;
  validate config; web GUI thêm auth + hàng đợi job; watch loop lưu state bền (không mất khi
  restart); retry/è lỗi rõ ràng; test tích hợp (sinh sample ffmpeg nhỏ); Docker đa kiến trúc;
  quét bảo mật/SBOM trong CI.
- [ ] **Phase 5 — Hợp nhất front-end + gỡ Windows-only.** Desktop GUI thành lớp mỏng gọi lõi
  `mkvtools` (hoặc bỏ nếu web GUI đủ); bỏ máy móc PyInstaller Windows-only hoặc thay bằng
  đóng gói đa nền tảng.

## Chạy thử nhanh (Phase 1)

```bash
pip install -e ".[dev]"        # cài lõi + công cụ test
pytest tests/test_splitter.py  # 5 test thuần, không cần ffmpeg
mkvtools probe phim.mkv        # xem kế hoạch tách (cần ffmpeg trên PATH)
mkvtools once phim.mkv --no-upload
docker compose up -d --build mkvtools   # pipeline tự động (Linux)
```

Xem thêm: [docs/mkvtools.md](docs/mkvtools.md).
