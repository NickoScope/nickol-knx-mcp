#!/usr/bin/env bash
# secret_scan.sh — echelon 2 of protection: scans the STAGED diff for secrets.
# Exit: 0 = clean, 1 = secret found (the commit must be blocked).
# Also installed as the pre-commit hook (install.sh wires it up).
set -uo pipefail

CONFIG_DIR="${CONFIG_DIR:-/config}"
LOG="$CONFIG_DIR/.git-sync/log"
ALLOWLIST="$CONFIG_DIR/.git-sync/scan_allowlist"   # exclusion lines (one per line)

# Only ADDED diff lines, without headers
DIFF="$(git diff --cached --unified=0 | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
[ -z "$DIFF" ] && exit 0

# Apply the allowlist (false positives are recorded THERE, not by disabling the scanner)
if [ -f "$ALLOWLIST" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && DIFF="$(echo "$DIFF" | grep -vF "$line" || true)"
  done < "$ALLOWLIST"
fi

PATTERNS=(
  # private keys
  '-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY'
  # cloud / API tokens of known formats
  'AKIA[0-9A-Z]{16}'                    # AWS access key
  'ghp_[A-Za-z0-9]{36}'                 # GitHub classic PAT
  'github_pat_[A-Za-z0-9_]{22,}'        # GitHub fine-grained PAT
  'xox[baprs]-[A-Za-z0-9-]{10,}'        # Slack
  'AIza[0-9A-Za-z_-]{35}'               # Google API key
  'sk-[A-Za-z0-9_-]{20,}'               # OpenAI/Anthropic-style
  'eyJhbGciOi[A-Za-z0-9_-]{20,}'        # JWT / HA long-lived token
  # a secret-looking field assigned a literal value NOT via !secret
  '(password|api_key|token|client_secret|bearer)["'"'"']?\s*[:=]\s*["'"'"']?[A-Za-z0-9_\-\.\+/=]{8,}'
)

HIT=""
for p in "${PATTERNS[@]}"; do
  # NOTE: "-e" is mandatory — BusyBox grep treats a pattern starting with "-" as an
  # option and silently skips it otherwise (LESSON-05, caught by a canary test).
  M="$(echo "$DIFF" | grep -inE -e "$p" | grep -viE '!secret|REDACTED|example|changeme|password_here' || true)"
  [ -n "$M" ] && HIT="$HIT
[$p]
$M"
done

if [ -n "$HIT" ]; then
  {
    echo "$(date '+%F %T') SECRET-SCAN BLOCKED COMMIT:"
    echo "$HIT" | head -40
    echo "--- False positive? Add the exact line to $ALLOWLIST"
  } >> "$LOG" 2>/dev/null || true
  echo "SECRET DETECTED — commit blocked. Details: $LOG" >&2
  exit 1
fi
exit 0
