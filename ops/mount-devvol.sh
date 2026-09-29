#!/bin/bash
# Mount the RecipesDev dev volume if it isn't already (D17).
#
# Run by the com.forkcast.mount-devvol LaunchAgent at login and on every
# volume-mount event, so /Volumes/Extreme SSD/stuff/forkcast (a symlink into
# this image) is live without anyone having to mount it by hand.
#
# NOTE: this script is version-controlled here, but launchd runs a COPY on the
# internal drive - it cannot run from inside the image it is responsible for
# mounting. ops/install-mount-agent.sh does that copy. Re-run the installer
# after editing this file.

SSD="/Volumes/Extreme SSD"
BUNDLE="$SSD/RecipesDev.sparsebundle"
DEVVOL="/Volumes/RecipesDev"

# Already mounted, or the SSD simply isn't plugged in: nothing to do. This
# fires on every mount event, so the quiet no-op is the common case.
[ -d "$DEVVOL/forkcast" ] && exit 0
[ -d "$BUNDLE" ] || exit 0

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

log "mounting $BUNDLE"
if hdiutil attach "$BUNDLE" >/dev/null 2>&1; then
  :
else
  # An unclean eject leaves lock/token behind and attach fails with
  # "Resource temporarily unavailable". Only safe to clear them once we've
  # confirmed no attached image is actually backed by this bundle.
  if hdiutil info | grep -qF "$BUNDLE"; then
    log "attach failed but the image is already attached - leaving lock alone"
    exit 1
  fi
  log "attach failed; clearing stale lock/token and retrying"
  rm -f "$BUNDLE/lock" "$BUNDLE/token"
  hdiutil attach "$BUNDLE" >/dev/null 2>&1 || { log "retry failed"; exit 1; }
fi

for _ in $(seq 1 10); do
  [ -d "$DEVVOL/forkcast" ] && { log "mounted"; exit 0; }
  sleep 1
done

log "attached but $DEVVOL/forkcast never appeared"
exit 1
