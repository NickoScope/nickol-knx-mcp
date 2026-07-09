#!/usr/bin/env bash
# install.sh — Circuit 1 bootstrap: a git repo in /config.
# Run ONCE from the SSH add-on. Requires: git, ssh, a created private repo and
# a deploy key (see references/setup.md §2). Idempotent.
set -euo pipefail

CONFIG_DIR="${CONFIG_DIR:-/config}"
REMOTE="${1:-}"   # git@github.com:YOUR_USER/ha-config.git
BRANCH="${GIT_BRANCH:-main}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[ -n "$REMOTE" ] || { echo "Usage: install.sh git@github.com:YOUR_USER/ha-config.git"; exit 1; }
command -v git >/dev/null || { echo "git not found — use the Advanced SSH & Web Terminal add-on"; exit 1; }

cd "$CONFIG_DIR"
mkdir -p .git-sync

# 1. The repository
if [ ! -d .git ]; then
  git init -q -b "$BRANCH"
  echo "[+] git init ($BRANCH)"
fi
git config user.name  "ha-git-backup"
git config user.email "ha-git-backup@config.local"
git remote get-url origin >/dev/null 2>&1 && git remote set-url origin "$REMOTE" || git remote add origin "$REMOTE"

# 2. .gitignore (echelon 1) — never overwrite an existing one
if [ ! -f .gitignore ]; then
  cp "$SCRIPT_DIR/../assets/gitignore.template" .gitignore
  echo "[+] .gitignore installed"
else
  echo "[i] .gitignore already exists — diff it against assets/gitignore.template manually"
fi

# 3. pre-commit hook (echelon 2)
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<EOF
#!/usr/bin/env bash
exec "$SCRIPT_DIR/secret_scan.sh"
EOF
chmod +x .git/hooks/pre-commit 2>/dev/null || true
chmod +x "$SCRIPT_DIR"/*.sh
echo "[+] pre-commit secret scan wired up"

# 4. SSH access check (deploy key)
if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "[+] deploy key works"
else
  echo "[!] SSH to GitHub failed — check the deploy key (references/setup.md §2)"
fi

# 4b. Context-independent SSH for git — CRITICAL.
# HA automations run ha_git_sync via shell_command in the CORE container, NOT this add-on.
# That container has its own (empty) known_hosts, so a push would fail "Host key verification
# failed" even though the deploy key is fine. Pin the key + a repo-local known_hosts into the
# repo's own git config so EVERY context (add-on, Core container, cron) uses the same, working ssh.
KEY="${DEPLOY_KEY:-/config/.git-sync/deploy_key}"
KH="$CONFIG_DIR/.git-sync/known_hosts"
ssh-keyscan -t ed25519,rsa github.com 2>/dev/null > "$KH" || true
git config core.sshCommand "ssh -i $KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$KH -o StrictHostKeyChecking=accept-new"
echo "[+] core.sshCommand pinned (host key works from any container, incl. Core)"

# 5. First pass: show WHAT would enter the repo, before any real commit
echo "[i] DRY-RUN — these files would land in the first commit:"
git add -A -n | head -50
echo "..."
echo "Review the list above for secrets. If it looks right, run:"
echo "  $SCRIPT_DIR/ha_git_sync.sh manual"
