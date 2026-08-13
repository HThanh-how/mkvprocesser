# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **XSS leo quyền (nghiêm trọng)** — `/classic` và `/analyze` ghép HTML bằng f-string,
  nên URL người dùng dán vào hàng đợi và tên file trong inbox đi thẳng vào trang. Một tài
  khoản `user` thêm link chứa `<script>` là script đó chạy trong **phiên của admin**. Chuyển
  sang Jinja2 autoescape (`mkvtools/templating.py` + `templates/`).
- **CSRF** — trước chỉ dựa vào `SameSite=Lax`. Thêm double-submit token (cookie `mkv_csrf`
  + header `X-CSRF-Token` hoặc field `csrf_token`); `web/csrf.js` lo cả `fetch()` lẫn form
  thường, kể cả form tạo động.
- **SSRF ở `/shorts/preview`** — endpoint nhận `?url` tuỳ ý rồi server tự tải và stream về
  trình duyệt. Nay chặn loopback/private/link-local/reserved sau khi resolve DNS.
- **Khoá tài khoản không đuổi được phiên đang mở** — `UserStore.get()` vẫn trả về dict cho
  tài khoản bị khoá nên middleware cho qua; người bị khoá dùng tiếp tới 7 ngày. Nay lọc
  `disabled` và thu hồi phiên khi khoá/xoá/đổi role/reset mật khẩu.
- Header bảo mật cho mọi response: CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`,
  `Permissions-Policy`; HSTS chỉ khi chạy HTTPS.
- systemd: bỏ root (`User=mkvtools`) + `ProtectSystem=strict`, `NoNewPrivileges`,
  `SystemCallFilter`, `MemoryHigh=80%` cho `mkvtools-gui`/`handoff`/`organize`.
- Khoá phiên bản có hash cho máy deploy (`deploy/requirements.lock`), `pip-audit`,
  Dependabot và CodeQL trong CI.

### Fixed
- **`process_video()` luôn ném `TypeError`** — hàm dùng `mux_subtitles`/`mux_subtitle_indices`
  trong thân nhưng thiếu ở chữ ký, trong khi cả 3 call site đều truyền chúng. Lỗi bị
  `except Exception` nuốt thành một dòng log chung chung, nên tính năng mux phụ đề của bản
  desktop chưa từng chạy.
- `splitter.plan()` khai `-> tuple` nhưng trả `dict`; `shorts.add()` dùng implicit Optional.
- `log_manager` dùng `datetime.utcnow()` (đã deprecate, trả datetime không có tzinfo).
- `install.sh` tự ghi một bản `mkvtools-gui.service` khác hẳn bản trong `deploy/` — cài lại
  là nhận bản yếu hơn. Nay chỉ còn một nguồn sự thật.

### Added
- Phiên đăng nhập bền qua restart (`work/sessions.json`, chỉ lưu SHA-256 của token) — máy
  tắt theo lịch mỗi tối không còn bắt mọi người đăng nhập lại.
- `GET /healthz` (công khai, tối giản) và `GET /metrics` (Prometheus, xác thực bằng phiên
  hoặc `X-MKV-Handoff-Token`).
- Log JSON một dòng mỗi bản ghi khi chạy dưới systemd, kèm `request_id` truy vết được.
- CI gộp một workflow: ruff toàn repo · pyright 17 module · test 3 OS × py3.9/3.12 ·
  cổng coverage 58% · pip-audit + kiểm lockfile còn khớp.
- Reorganized project structure following Python package standards
- Entry points at root for backward compatibility
- CONTRIBUTING.md and CODE_OF_CONDUCT.md documentation
- LICENSE file (MIT)
- GitHub issue and PR templates
- CI/CD workflow template

### Changed
- Moved core modules to `src/mkvprocessor/`
- Moved GUI modules to `src/gui/`
- Moved build scripts to `scripts/`
- Moved utility scripts to `tools/`
- Updated all documentation to English

## [2.0.0] - 2024-XX-XX

### Added
- PySide6 GUI with full feature set
- Automatic video metadata detection and processing
- Multi-language support (Vietnamese, English, Chinese, etc.)
- Automatic subtitle extraction
- Smart file naming with metadata
- GitHub sync integration
- Auto-commit subtitles

### Changed
- Improved processing performance
- Optimized memory usage
- Enhanced error handling

## [1.0.0] - 2024-XX-XX

### Added
- Core MKV processing functionality
- Basic GUI with tkinter
- FFmpeg integration
- File organization features
