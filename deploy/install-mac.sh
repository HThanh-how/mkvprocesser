#!/bin/zsh
# Chay tren Mac mini sau khi bat System Settings > General > Sharing > Remote Login.
set -eu

INSTALL_DIR=${INSTALL_DIR:-/opt/mkvprocesser}
DATA_DIR=${DATA_DIR:-/Users/Shared/mkvtools}
GUI_PORT=${GUI_PORT:-8800}
HANDOFF_TOKEN=${HANDOFF_TOKEN:-}
[ ${#HANDOFF_TOKEN} -ge 24 ] || {
  echo "Can chay voi HANDOFF_TOKEN do vnpt cap" >&2
  exit 1
}

command -v brew >/dev/null || {
  echo "Can Homebrew: https://brew.sh" >&2
  exit 1
}
brew install ffmpeg python@3.13 aria2 || true
sudo mkdir -p "$INSTALL_DIR" "$DATA_DIR"/{inbox,work,done,downloads,secrets}
sudo chown -R "$(id -un)":staff "$INSTALL_DIR" "$DATA_DIR"

if [ ! -d "$INSTALL_DIR/.git" ]; then
  git clone --branch develop --single-branch https://github.com/HThanh-how/mkvprocesser "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
git fetch origin develop
git checkout develop
git pull --ff-only origin develop
python3.13 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e '.[upload,web,fetch,cache]'
cp deploy/config.mac.yaml config.yaml

cat > "$HOME/Library/LaunchAgents/com.vnpt.mkvtools.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.vnpt.mkvtools</string>
  <key>ProgramArguments</key><array><string>$INSTALL_DIR/.venv/bin/mkvtools-gui</string></array>
  <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>MKV_CONFIG</key><string>$INSTALL_DIR/config.yaml</string>
    <key>MKV_GUI_HOST</key><string>0.0.0.0</string>
    <key>MKV_GUI_PORT</key><string>$GUI_PORT</string>
    <key>MKV_NODE_ID</key><string>mac</string>
    <key>MKV_WORKER_START_HOUR</key><string>18</string>
    <key>MKV_WORKER_STOP_HOUR</key><string>6</string>
    <key>MKV_HANDOFF_TOKEN</key><string>$HANDOFF_TOKEN</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DATA_DIR/work/service.log</string>
  <key>StandardErrorPath</key><string>$DATA_DIR/work/service-error.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/com.vnpt.mkvtools" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.vnpt.mkvtools.plist"

printf '%s\n' "$HANDOFF_TOKEN" > "$DATA_DIR/handoff.token"
chmod 600 "$DATA_DIR/handoff.token"
PYTHON_BIN=$(command -v python3.13)
cat > "$HOME/Library/LaunchAgents/com.vnpt.mkvtools-handoff.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.vnpt.mkvtools-handoff</string>
  <key>ProgramArguments</key><array>
    <string>$PYTHON_BIN</string><string>$INSTALL_DIR/deploy/handoff.py</string>
    <string>--source</string><string>http://127.0.0.1:$GUI_PORT</string>
    <string>--dest</string><string>http://vnpt:8800</string>
    <string>--token-file</string><string>$DATA_DIR/handoff.token</string>
    <string>--start-hour</string><string>6</string>
    <string>--stop-hour</string><string>18</string>
  </array>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$DATA_DIR/work/handoff.log</string>
  <key>StandardErrorPath</key><string>$DATA_DIR/work/handoff-error.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/com.vnpt.mkvtools-handoff" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.vnpt.mkvtools-handoff.plist"
echo "mkvtools Mac: http://127.0.0.1:$GUI_PORT"
