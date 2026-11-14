#!/bin/bash
# Install the com.forkcast.backend LaunchAgent (D18): the backend starts at
# login and is restarted if it dies, so the phone PWA (Tailscale serve ->
# :8000) works whenever the Mac is on, with no terminal session open.
#
# Same copy pattern as the D17 mount launcher: launchd runs a COPY of
# run-backend.sh from the internal drive, because that script mounts the very
# volume it lives on. Re-run this installer after editing run-backend.sh.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/run-backend.sh"
DEST_DIR="$HOME/Library/Application Support/forkcast"
PLIST="$HOME/Library/LaunchAgents/com.forkcast.backend.plist"
LOG="$HOME/Library/Logs/forkcast-backend.log"

mkdir -p "$DEST_DIR" "$HOME/Library/LaunchAgents"
cp "$SRC" "$DEST_DIR/run-backend.sh"
chmod +x "$DEST_DIR/run-backend.sh"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.forkcast.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DEST_DIR/run-backend.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <!-- With the SSD unplugged the mount fails fast; don't hammer hdiutil. -->
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.forkcast.backend" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed and started: com.forkcast.backend"
echo "Script copy: $DEST_DIR/run-backend.sh"
echo "Logs:        $LOG"
echo "Stop with:   launchctl bootout gui/\$(id -u)/com.forkcast.backend"
