#!/usr/bin/env bash
# ha_git_sync.sh — Circuit 1: git sync /config → GitHub
# Usage: ha_git_sync.sh [trigger]   trigger: manual|daily|pre-update|restart
# Exit: 0 = ok/nothing-to-do, 1 = error (recorded in the status file)
set -uo pipefail

CONFIG_DIR="${CONFIG_DIR:-/config}"
SYNC_DIR="$CONFIG_DIR/.git-sync"
LOG="$SYNC_DIR/log"
STATUS="$SYNC_DIR/last_status"      # read by the HA command_line sensor
LOCKFILE="/tmp/ha_git_sync.lock"
TRIGGER="${1:-manual}"
BRANCH="${GIT_BRANCH:-main}"
RETRIES=3

mkdir -p "$SYNC_DIR"
log() { echo "$(date '+%F %T') [$TRIGGER] $*" >> "$LOG"; }
fail() { echo "error: $*" > "$STATUS"; log "FAIL: $*"; exit 1; }
ok()   { echo "ok: $*"    > "$STATUS"; log "OK: $*";   exit 0; }

# --- lock: no parallel runs ---------------------------------------------------
exec 9>"$LOCKFILE"
flock -n 9 || fail "another sync is running"

cd "$CONFIG_DIR" || fail "no $CONFIG_DIR"
[ -d .git ] || fail "not a git repo — run install.sh first"

# --- any changes? --------------------------------------------------------------
git add -A
if git diff --cached --quiet; then
  ok "clean, nothing to commit"
fi

# --- secret scanner (echelon 2) -----------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! "$SCRIPT_DIR/secret_scan.sh"; then
  git reset -q  # unstage everything, commit nothing
  fail "SECRET DETECTED in staged diff — commit blocked, see $LOG"
fi

# --- a meaningful commit --------------------------------------------------------
HA_VER="unknown"
[ -f .HA_VERSION ] && HA_VER="$(cat .HA_VERSION)"
NFILES=$(git diff --cached --name-only | wc -l | tr -d ' ')
SUMMARY="[$TRIGGER] $NFILES file(s) | HA $HA_VER"
BODY="$(git diff --cached --stat | tail -20)"

git commit -q -m "$SUMMARY" -m "$BODY" || fail "commit failed"
log "committed: $SUMMARY"

# --- tag before an update -------------------------------------------------------
if [ "$TRIGGER" = "pre-update" ]; then
  TAG="pre-update/$(date +%Y-%m-%d_%H%M)"
  git tag -f "$TAG" && log "tagged $TAG"
fi

# --- push with retry and exponential backoff ------------------------------------
n=0
until git push -q origin "$BRANCH" --tags 2>>"$LOG"; do
  n=$((n+1))
  [ $n -ge $RETRIES ] && fail "push failed after $RETRIES attempts (commit is local, next run will push it)"
  sleep $((5 * 2 ** n))
done

ok "$SUMMARY pushed"
