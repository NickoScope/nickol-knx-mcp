#!/usr/bin/env bash
# backup_offsite.sh — Circuit 2: freshest native HA backup → age encryption →
# GitHub Release in the ha-config repo. Rotation: keep the KEEP latest releases.
# Requires: age, curl, a fine-grained PAT (Contents RW of ONE repo) in
# /config/.git-sync/gh_token, the public age key in /config/.git-sync/age_recipient
set -euo pipefail

CONFIG_DIR="${CONFIG_DIR:-/config}"
BACKUP_DIR="${BACKUP_DIR:-/backup}"          # native backup path on supervised/HAOS
REPO="${GH_REPO:?export GH_REPO=user/ha-config}"
KEEP="${KEEP:-8}"
TOKEN="$(cat "$CONFIG_DIR/.git-sync/gh_token")"
RECIPIENT="$(cat "$CONFIG_DIR/.git-sync/age_recipient")"
API="https://api.github.com/repos/$REPO"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json")
LOG="$CONFIG_DIR/.git-sync/log"
log(){ echo "$(date '+%F %T') [offsite] $*" >> "$LOG"; }

# 1. The freshest native backup (creating it is the HA automation's job, before this call)
LATEST="$(ls -t "$BACKUP_DIR"/*.tar 2>/dev/null | head -1)"
[ -n "$LATEST" ] || { log "FAIL: no .tar in $BACKUP_DIR"; exit 1; }

# 2. Encrypt (the HA tarball may already be password-encrypted — age on top is fine)
STAMP="$(date +%Y-%m-%d_%H%M)"
ENC="/tmp/ha-backup-$STAMP.tar.age"
age -r "$RECIPIENT" -o "$ENC" "$LATEST"
SIZE=$(du -m "$ENC" | cut -f1)
[ "$SIZE" -lt 1900 ] || { log "FAIL: $SIZE MB > GitHub Releases limit (2GB) — exclude media from the backup"; rm -f "$ENC"; exit 1; }

# 3. Create the release
TAG="backup/$STAMP"
REL_JSON="$(curl -sf "${AUTH[@]}" -X POST "$API/releases" \
  -d "{\"tag_name\":\"$TAG\",\"name\":\"HA backup $STAMP\",\"body\":\"age-encrypted, $SIZE MB\"}")"
REL_ID="$(echo "$REL_JSON" | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*')"
[ -n "$REL_ID" ] || { log "FAIL: release create"; rm -f "$ENC"; exit 1; }

# 4. Upload the asset
curl -sf "${AUTH[@]}" -H "Content-Type: application/octet-stream" \
  --data-binary @"$ENC" \
  "https://uploads.github.com/repos/$REPO/releases/$REL_ID/assets?name=$(basename "$ENC")" >/dev/null \
  || { log "FAIL: asset upload"; rm -f "$ENC"; exit 1; }
rm -f "$ENC"
log "OK: $TAG uploaded ($SIZE MB)"

# 5. Rotation: delete backup/* releases beyond KEEP (and their tags)
curl -sf "${AUTH[@]}" "$API/releases?per_page=100" \
 | grep -oE '"tag_name": *"backup/[^"]*"|"id": *[0-9]*' \
 | paste - - | grep 'backup/' | sort -r | tail -n +$((KEEP+1)) \
 | while read -r idline tagline; do
     RID="$(echo "$idline" | grep -o '[0-9]*')"
     RTAG="$(echo "$tagline" | sed 's/.*"backup/backup/;s/"//g')"
     curl -sf "${AUTH[@]}" -X DELETE "$API/releases/$RID" >/dev/null || true
     curl -sf "${AUTH[@]}" -X DELETE "$API/git/refs/tags/$RTAG" >/dev/null || true
     log "rotated out: $RTAG"
   done
echo "ok: offsite $TAG" > "$CONFIG_DIR/.git-sync/last_offsite"
