#!/bin/bash
# =============================================================================
# mkvtools — dung toan bo he thong tren 1 may Debian/Ubuntu (chay voi quyen root).
#
#   git clone <repo> /opt/mkvprocesser && cd /opt/mkvprocesser && bash deploy/install.sh
#
# Tao: venv + cai package, Playwright Chromium, aria2, stack "Bat tay"
# (Xvfb + Chromium-CDP + x11vnc + noVNC), Redis (tuy chon), va 6 systemd unit:
#   mkvtools-gui · mkv-xvfb · mkv-chromium · mkv-x11vnc · mkv-novnc · mkv-organize.timer
# Bien moi truong dieu chinh: INSTALL_DIR, DATA_DIR, GUI_PORT, ADMINPASS, VNCPASS.
# =============================================================================
set -e
INSTALL_DIR=${INSTALL_DIR:-/opt/mkvprocesser}
DATA_DIR=${DATA_DIR:-/data}
GUI_PORT=${GUI_PORT:-8800}
NODE_ID=${NODE_ID:-$(hostname)}
WORKER_START_HOUR=${WORKER_START_HOUR:-0}
WORKER_STOP_HOUR=${WORKER_STOP_HOUR:-24}
HANDOFF_DEST=${HANDOFF_DEST:-}
SVC_USER=${SVC_USER:-mkvtools}
export DEBIAN_FRONTEND=noninteractive
_rand() { head -c12 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c12; }
ADMINPASS=${ADMINPASS:-$(_rand)}
VNCPASS=${VNCPASS:-$(_rand)}
HANDOFF_TOKEN=${HANDOFF_TOKEN:-$(_rand)$(_rand)}

echo "== [1/7] apt deps =="
apt-get update -qq
apt-get install -y -qq ffmpeg python3-venv python3-pip git aria2 fonts-liberation \
  xvfb x11vnc novnc websockify chromium 2>/dev/null \
  || apt-get install -y -qq ffmpeg python3-venv python3-pip git aria2 fonts-liberation \
       xvfb x11vnc novnc websockify chromium-browser
apt-get install -y -qq redis-server 2>/dev/null || true   # tuy chon (khong co -> cache file)
CHROME=$(command -v chromium || command -v chromium-browser)

echo "== [2/7] venv + mkvtools[all] =="
cd "$INSTALL_DIR"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
# Mac dinh cai theo deploy/requirements.lock (pin + hash) de hai lan cai cach
# nhau vai thang ra dung mot bo thu vien. LOCKED=0 de cai theo khoang trong
# pyproject (vd khi thu thu vien moi, hoac lock chua kip cap nhat).
if [ "${LOCKED:-1}" = "1" ] && [ -f deploy/requirements.lock ]; then
  .venv/bin/pip install -q --require-hashes -r deploy/requirements.lock
  .venv/bin/pip install -q -e . --no-deps        # deps da khoa o tren
else
  echo "   (LOCKED=0 — cai theo khoang trong pyproject, khong tai lap duoc)"
  .venv/bin/pip install -q -e ".[all]"
fi
.venv/bin/playwright install chromium 2>/dev/null \
  || .venv/bin/playwright install --with-deps chromium || true

echo "== [3/7] thu muc du lieu + config + user dich vu =="
mkdir -p "$DATA_DIR"/{inbox,work,done,downloads,catch-profile} "$INSTALL_DIR"/secrets
[ -f "$INSTALL_DIR/config.yaml" ] || cp "$INSTALL_DIR/deploy/config.lxc.yaml" "$INSTALL_DIR/config.yaml"
# Tai khoan he thong rieng cho mkvtools-gui: service chay ffmpeg/yt-dlp/aria2
# tren du lieu tai tu Internet, khong co ly do gi de no chay bang root.
id -u "$SVC_USER" >/dev/null 2>&1 || useradd --system --no-create-home \
  --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SVC_USER"
chown -R "$SVC_USER:$SVC_USER" "$INSTALL_DIR" "$DATA_DIR"

echo "== [4/7] secrets (/etc/mkvtools.env) =="
x11vnc -storepasswd "$VNCPASS" /etc/x11vnc.pass >/dev/null
cat > /etc/mkvtools.env <<EOF
MKV_CONFIG=$INSTALL_DIR/config.yaml
MKV_GUI_HOST=0.0.0.0
MKV_GUI_PORT=$GUI_PORT
MKV_ADMIN_USER=admin
MKV_ADMIN_PASS=$ADMINPASS
MKV_VNC_PASSWORD=$VNCPASS
MKV_NODE_ID=$NODE_ID
MKV_WORKER_START_HOUR=$WORKER_START_HOUR
MKV_WORKER_STOP_HOUR=$WORKER_STOP_HOUR
MKV_HANDOFF_TOKEN=$HANDOFF_TOKEN
EOF
chmod 600 /etc/mkvtools.env
printf '%s\n' "$HANDOFF_TOKEN" > /etc/mkvtools-handoff.token
chmod 600 /etc/mkvtools-handoff.token
# handoff.service chay bang $SVC_USER nen phai doc duoc token (van 0600).
chown "$SVC_USER:$SVC_USER" /etc/mkvtools-handoff.token 2>/dev/null || true

echo "== [5/7] systemd units =="
cat > /etc/systemd/system/mkv-xvfb.service <<EOF
[Unit]
Description=mkvtools catch - Xvfb :99
[Service]
ExecStart=/usr/bin/Xvfb :99 -screen 0 1366x768x24 -ac
Restart=always
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mkv-chromium.service <<EOF
[Unit]
Description=mkvtools catch - Chromium (CDP 9222) on :99
After=mkv-xvfb.service
Requires=mkv-xvfb.service
[Service]
Environment=DISPLAY=:99
ExecStart=$CHROME --no-sandbox --disable-gpu --disable-dev-shm-usage --user-data-dir=$DATA_DIR/catch-profile --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check --start-maximized --window-size=1366,768 about:blank
Restart=always
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mkv-x11vnc.service <<EOF
[Unit]
Description=mkvtools catch - x11vnc for :99
After=mkv-xvfb.service
Requires=mkv-xvfb.service
[Service]
ExecStart=/usr/bin/x11vnc -display :99 -forever -shared -rfbauth /etc/x11vnc.pass -rfbport 5900 -localhost -noxdamage
Restart=always
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mkv-novnc.service <<EOF
[Unit]
Description=mkvtools catch - noVNC web viewer on 6080
After=mkv-x11vnc.service
[Service]
ExecStart=/usr/bin/websockify --web=/usr/share/novnc 6080 localhost:5900
Restart=always
[Install]
WantedBy=multi-user.target
EOF
# Unit cua GUI lay tu deploy/mkvtools-gui.service (co san sandbox). Truoc day
# file nay ghi mot ban INLINE khac han ban trong deploy/ — hai dinh nghia troi
# nhau, ban duoc cai lai la ban yeu hon. Nay chi con mot nguon su that; sed chi
# de ton trong INSTALL_DIR/DATA_DIR/SVC_USER khi nguoi dung doi mac dinh.
sed -e "s#/opt/mkvprocesser#$INSTALL_DIR#g" \
    -e "s#/data#$DATA_DIR#g" \
    -e "s#^\(User\|Group\)=mkvtools\$#\1=$SVC_USER#" \
    "$INSTALL_DIR/deploy/mkvtools-gui.service" \
    > /etc/systemd/system/mkvtools-gui.service
chmod 644 /etc/systemd/system/mkvtools-gui.service
cat > /etc/systemd/system/mkv-organize.service <<EOF
[Unit]
Description=mkvtools organize (private + playlists; budget tu config organize_budget)
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=-/etc/mkvtools.env
ExecStart=$INSTALL_DIR/.venv/bin/mkvtools organize
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=$DATA_DIR $INSTALL_DIR
EOF
cat > /etc/systemd/system/mkv-organize.timer <<EOF
[Unit]
Description=Run mkvtools organize daily (budgeted)
[Timer]
OnCalendar=*-*-* 16:00:00
Persistent=true
RandomizedDelaySec=600
[Install]
WantedBy=timers.target
EOF
if [ -n "$HANDOFF_DEST" ]; then
  install -m 0644 "$INSTALL_DIR/deploy/mkvtools-handoff.service" \
    /etc/systemd/system/mkvtools-handoff.service
  install -m 0644 "$INSTALL_DIR/deploy/mkvtools-handoff.timer" \
    /etc/systemd/system/mkvtools-handoff.timer
  printf 'MKV_HANDOFF_SOURCE=http://127.0.0.1:%s\nMKV_HANDOFF_DEST=%s\n' \
    "$GUI_PORT" "$HANDOFF_DEST" > /etc/mkvtools-handoff.env
  chmod 600 /etc/mkvtools-handoff.env   # systemd doc file nay bang root, giu root
fi

echo "== [6/7] bat dich vu =="
systemctl daemon-reload
systemctl enable --now mkv-xvfb mkv-chromium mkv-x11vnc mkv-novnc mkvtools-gui mkv-organize.timer
[ -z "$HANDOFF_DEST" ] || systemctl enable --now mkvtools-handoff.timer

echo "== [7/7] XONG =="
IP=$(hostname -I | awk '{print $1}')
echo "  GUI    : http://$IP:$GUI_PORT     (admin / $ADMINPASS)"
echo "  noVNC  : http://$IP:6080          (VNC pass: $VNCPASS)"
echo "  >> Luu 2 mat khau tren. Doi mat khau admin qua menu Tai khoan sau khi dang nhap."
echo "  >> secrets/client_secret.json + token.json can copy tay (OAuth YouTube)."
