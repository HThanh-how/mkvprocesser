# Deploy mkvtools (server / LXC)

Dựng **toàn bộ** hệ thống trên 1 máy Debian/Ubuntu bằng **1 lệnh** — để khi container/máy chết là tái lập lại được ngay (không phải setup tay).

## Cài nhanh

```bash
git clone <repo-url> /opt/mkvprocesser
cd /opt/mkvprocesser
sudo bash deploy/install.sh
```

Tuỳ chỉnh (biến môi trường, đều có mặc định):

```bash
sudo INSTALL_DIR=/opt/mkvprocesser DATA_DIR=/data GUI_PORT=8800 \
     ADMINPASS='matkhau-admin' VNCPASS='matkhau-vnc' bash deploy/install.sh
```

Script in ra URL + mật khẩu admin/VNC ở cuối. **Lưu lại** rồi đổi mật khẩu admin trong **menu Tài khoản**.

## Nó cài gì
- apt: `ffmpeg python3-venv aria2 xvfb x11vnc novnc websockify chromium` (+ `redis-server` nếu được).
- `.venv` + `pip install -e .[all]` + `playwright install chromium`.
- Thư mục `/data/{inbox,work,done,downloads,catch-profile}` + `config.yaml` (từ `deploy/config.lxc.yaml`).
- Secrets sinh ngẫu nhiên ghi vào `/etc/mkvtools.env` (chmod 600) — **không nằm trong repo**.
- 6 systemd unit:

| Unit | Việc | Cổng |
|---|---|---|
| `mkvtools-gui` | Web GUI (hàng đợi, video, cài đặt, login) | 8800 |
| `mkv-xvfb` | màn hình ảo :99 cho "Bắt tay" | — |
| `mkv-chromium` | Chromium điều khiển-tay (CDP) | 9222 (localhost) |
| `mkv-x11vnc` | VNC cho :99 | 5900 (localhost) |
| `mkv-novnc` | noVNC (nhúng vào GUI) | 6080 |
| `mkv-organize.timer` | dọn kênh hằng ngày (private + playlist, có budget) | — |

## Chạy bằng tài khoản riêng (không phải root)

`mkvtools-gui`, `mkvtools-handoff` và `mkv-organize` chạy dưới user hệ thống
`mkvtools` (đổi bằng `SVC_USER=...`), kèm sandbox systemd: `ProtectSystem=strict`,
`NoNewPrivileges`, `PrivateTmp`, `RestrictAddressFamilies`, `SystemCallFilter`,
`MemoryHigh=80%`. Lý do: các service này chạy ffmpeg/yt-dlp/aria2/Chromium trên
dữ liệu tải từ Internet — một lỗi parse trong ffmpeg không nên đổi thành root.

**Nâng cấp từ bản cũ (đang chạy root)** — chạy trước khi `systemctl restart`:

```bash
useradd --system --no-create-home --home-dir /opt/mkvprocesser --shell /usr/sbin/nologin mkvtools
chown -R mkvtools:mkvtools /opt/mkvprocesser /data
chown mkvtools:mkvtools /etc/mkvtools-handoff.token
systemctl daemon-reload && systemctl restart mkvtools-gui
systemd-analyze security mkvtools-gui     # kiểm điểm exposure
```

Nếu service không lên, gần như luôn là quyền ghi: xem `journalctl -u mkvtools-gui -n50`,
tìm `Read-only file system` rồi thêm đường dẫn đó vào `ReadWritePaths=`.

**Cố ý KHÔNG sandbox hai unit này:**

| Unit | Vì sao để nguyên |
|---|---|
| `mkvtools-vnpt-stop` | `pct shutdown` cần root thật + `/etc/pve` (fuse). Đây là cơ chế tắt sạch container trước giờ cắt điện — hỏng nghĩa là mất dữ liệu, không đáng đánh đổi. |
| `mkv-xvfb` / `mkv-chromium` / `mkv-x11vnc` | Chromium `--no-sandbox` chạy root là điểm yếu đã biết, nhưng đổi user ở đây dễ làm hỏng chuỗi X11/CDP mà không test được từ xa. Xem ROADMAP. |

## Sau khi cài (thủ công, vì là secret)
Copy OAuth YouTube vào `secrets/`:
```
secrets/client_secret.json     # OAuth Desktop client (Google Cloud Console)
secrets/token.json             # tạo lần đầu: .venv/bin/mkvtools sync-titles (hoặc once)
```

## Quản lý
```bash
systemctl status mkvtools-gui
systemctl restart mkvtools-gui
journalctl -u mkvtools-gui -f
systemctl list-timers mkv-organize.timer
```

## Ghi chú
- **Proxmox LXC**: nếu chạy trong container, `redis-server` có thể không start (systemd hardening) → tool **tự fallback cache file**, vẫn tiết kiệm quota như thường.
- **Tên gói Chromium**: Debian = `chromium` (`/usr/bin/chromium`); Ubuntu có thể là `chromium-browser` — script tự dò.
- **Truy cập từ xa**: GUI bind `0.0.0.0` → vào qua LAN. Muốn qua Tailscale, dùng `tailscale serve` hoặc cài tailscale trong container.
