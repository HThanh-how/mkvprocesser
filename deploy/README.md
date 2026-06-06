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
