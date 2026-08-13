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
  idempotency.py     # dedup bằng chữ ký SHA‑256 + store bền đĩa         [x]
  titlematch.py      # chống trùng theo TỰA (nhẹ; phân biệt Phần 1/2/3)  [x]
  resources.py       # kiểm tra đĩa/RAM, chọn work-dir (đa nền tảng)     [x]
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
- [~] **Phase 3 — Port phần "thông minh".** ✅ idempotency (chữ ký SHA‑256 + store bền đĩa,
  **fix bug watch reset khi restart**) và resource-aware (đĩa/RAM, đa nền tảng) đã port,
  nối vào pipeline/cli/webui, có test. Tiện thể fix env override không ép kiểu (MKV_UPLOAD=false
  giờ thành False thật). ⏳ Còn: GitHub‑sync (opt-in).
- [~] **Phase 4 — Gia cố enterprise.** ✅ Lazy-import tách extras thật (cài lõi chỉ cần PyYAML;
  google/fastapi vào [upload]/[web]; CI chứng minh import lõi không cần chúng); ✅ validate config
  (enum + poll_seconds); ✅ web GUI auth token tùy chọn (MKV_GUI_TOKEN); watch state bền đã làm ở P3.
  ✅ **Đợt gia cố 13/08/2026**: XSS/CSRF/SSRF + header bảo mật; template Jinja2 autoescape;
  session bền đĩa + thu hồi phiên khi khoá tài khoản; systemd sandbox + bỏ root; `/healthz`
  + `/metrics` + log JSON có request-id; lockfile pin+hash cho deploy; dependabot + pip-audit
  + CodeQL; ruff sạch toàn repo + pyright cho 17 module + cổng coverage 58%.
  ⏳ Còn: hàng đợi job cho web GUI, test tích hợp (sinh sample ffmpeg nhỏ), Docker đa kiến trúc, SBOM.

### Nợ kỹ thuật đã biết (cố ý hoãn, không phải bỏ quên)

| # | Việc | Vì sao hoãn | Cách làm khi tới lượt |
|---|---|---|---|
| 1 | **Bundle Tailwind, bỏ CDN** | Cần build step (npm/tailwindcli) | Mọi trang — kể cả `/admin`, `/settings` — nạp `cdn.tailwindcss.com`. CDN bị chiếm = chiếm phiên admin. Bundle vào `web/`, tách `<script>` inline ra file, rồi mới siết được CSP (bỏ `unsafe-inline`/`unsafe-eval`). |
| 2 | **`/opt` chỉ-đọc** | App ghi `secrets/` và `ui_settings.json` ngay trong thư mục cài | Chuyển `config.yaml` + `secrets/` sang `/data`, rồi thu `ReadWritePaths` trong `mkvtools-gui.service` còn `/data`. |
| 3 | **Chromium chạy root `--no-sandbox`** | Đổi user dễ hỏng chuỗi X11/CDP, không test được từ xa | Chuyển `mkv-chromium`/`mkv-xvfb`/`mkv-x11vnc` sang user `mkvtools`, kiểm bằng noVNC + một lần "Bắt tay" thật. |
| 4 | **`metadata_loader` parse rồi vứt** | Phải đổi chữ ký `metadata_loaded_signal` | `resolution`/`year` được parse ở thread nền rồi bỏ, main thread vẫn đọc lại (xem FIXME trong file). Cho hai giá trị đi kèm signal. |
| 5 | **Hiện đại hoá type hint ở legacy** | ~115 chỗ trong `mkvprocessor`/`gui`, sắp bị xoá | Đã tắt `UP006/UP007/UP035/UP045` cho hai cây đó trong `pyproject.toml`. Xoá per-file-ignore cùng lúc xoá code. |
| 6 | **Coverage `cli.py`/`uploader.py` = 0%** | Cần fake Google API + runner CLI | Kéo ngưỡng coverage lên trên 58% sau khi phủ hai file này. |
| 7 | **`git filter-repo` xoá blob ffmpeg** | Viết lại lịch sử = phải force-push, ảnh hưởng mọi bản clone | ~190MB `.exe` vẫn nằm trong lịch sử (Phase 2). Chỉ làm khi thống nhất được thời điểm với mọi người đang clone. |
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
