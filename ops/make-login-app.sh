#!/bin/bash
# Build the "Mount Forkcast" login launcher (D17).
#
# Installs a runtime copy of mount-devvol.sh on the internal drive and wraps it
# in a tiny AppleScript .app. Add that app to System Settings > General >
# Login Items so the dev volume is mounted at login and the
# stuff/forkcast symlink is live without anyone double-clicking anything.
#
# Why an .app and not the .command: a .command added as a Login Item opens a
# Terminal window at every login. The .app runs silently.
#
# Why a copy: launchd/Login Items cannot run the script from inside the image
# it is responsible for mounting. Re-run this after editing mount-devvol.sh.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/mount-devvol.sh"
DEST_DIR="$HOME/Library/Application Support/forkcast"
APP="$HOME/Applications/Mount Forkcast.app"

mkdir -p "$DEST_DIR" "$HOME/Applications"
cp "$SRC" "$DEST_DIR/mount-devvol.sh"
chmod +x "$DEST_DIR/mount-devvol.sh"

TMP="$(mktemp -t mountforkcast).applescript"
printf '%s\n' 'do shell script "\"$HOME/Library/Application Support/forkcast/mount-devvol.sh\""' > "$TMP"
rm -rf "$APP"
osacompile -o "$APP" "$TMP"
rm -f "$TMP"

echo "Built: $APP"
echo "Script: $DEST_DIR/mount-devvol.sh"
echo
echo "Add it to login: System Settings > General > Login Items > '+' > $APP"
echo "Test it now with: open -W \"$APP\""
