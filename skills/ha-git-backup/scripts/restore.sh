#!/usr/bin/env bash
# restore.sh — recovery. Two scenarios:
#   restore.sh file   — roll back files from git (Circuit 1)
#   restore.sh full   — full restore from a GitHub Release (Circuit 2)
# Also used for the monthly restore drill (references/restore-runbook.md)
set -euo pipefail
MODE="${1:-help}"

case "$MODE" in
file)
  cd "${CONFIG_DIR:-/config}"
  echo "Recent commits:"; git log --oneline -15
  echo
  echo "Roll back one file:    git checkout <sha> -- <file>"
  echo "Roll back everything:  git reset --hard <sha>   (DESTRUCTIVE: wipes uncommitted changes)"
  echo "What changed:          git diff <sha> --stat"
  echo "After rollback: validate the config (ha core check) and restart HA."
  ;;
full)
  REPO="${GH_REPO:?export GH_REPO=user/ha-config}"
  KEYFILE="${AGE_KEY:?export AGE_KEY=/path/to/age_key.txt}"
  echo "=== FULL RESTORE (Circuit 2) ==="
  echo "1. List backups:   gh release list -R $REPO   (or the /releases API)"
  echo "2. Download asset: gh release download <backup/TAG> -R $REPO -D /tmp"
  echo "3. Decrypt:        age -d -i $KEYFILE -o restored.tar /tmp/ha-backup-*.tar.age"
  echo "4. Verify:         tar -tf restored.tar | grep -c . && tar -tf restored.tar | grep core.config_entries"
  echo "5. HAOS: place restored.tar in /backup and restore via the UI"
  echo "   (Settings → System → Backups), or onboarding-restore on a fresh install."
  echo "6. After start: verify entity registry, auth, dashboards, ESPHome nodes."
  echo
  echo "DRILL mode: run steps 1-4 WITHOUT step 5, record the date in .git-sync/last_drill"
  ;;
*)
  echo "Usage: restore.sh file|full"; exit 1;;
esac
