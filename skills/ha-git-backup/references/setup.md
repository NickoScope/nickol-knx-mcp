# Installation from scratch

## §1. Prerequisites
- HA OS / Supervised with the **Advanced SSH & Web Terminal** add-on (it ships git and ssh).
- A private repo `ha-config` on GitHub (empty, no README).
- Copy the skill's scripts to `/config/.git-sync/bin/` and the gitignore template to
  `/config/.git-sync/assets/`, then `chmod +x` the scripts.
- Note: with `sftp: false` in the add-on config, `scp` won't work — use a tar pipe:
  `tar cz scripts | ssh <your-ha-host> 'cd /tmp && tar xz'`.

## §2. Deploy key (Circuit 1) — NOT a PAT
```bash
ssh-keygen -t ed25519 -f /config/.git-sync/deploy_key -N "" -C "ha-git-backup"
cat /config/.git-sync/deploy_key.pub
```
GitHub → repo `ha-config` → Settings → Deploy keys → Add key → **Allow write access**.

SSH config so git picks exactly this key:
```bash
mkdir -p ~/.ssh && cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile /config/.git-sync/deploy_key
  IdentitiesOnly yes
EOF
```
Why a deploy key: it grants access to ONE repo. A compromised key ≠ a compromised GitHub
account (unlike a classic PAT with the `repo` scope).

## §3. Circuit 1: install
```bash
/config/.git-sync/bin/install.sh git@github.com:YOUR_USER/ha-config.git
# review the dry-run file list for secrets, then:
/config/.git-sync/bin/ha_git_sync.sh manual
```
Add `assets/configuration_snippet.yaml` and `assets/automations.yaml`, **fully restart HA**
(quick reload does not load `shell_command`/`command_line`), check `sensor.git_sync_status`.

## §4. Circuit 2: offsite to GitHub Releases
1. **age key** (generate NOT on HA but on your workstation):
   `age-keygen -o age_key.txt` → store the private key offline (password manager / paper).
   Only the public half goes to HA:
   `echo "age1..." > /config/.git-sync/age_recipient`
2. **Fine-grained PAT**: GitHub → Settings → Developer settings → Fine-grained tokens →
   access to `ha-config` only, permission **Contents: Read and write**. 1-year expiry,
   calendar reminder to rotate.
   `echo "github_pat_..." > /config/.git-sync/gh_token && chmod 600 /config/.git-sync/gh_token`
3. `age` inside the SSH add-on container: add `age` to the add-on's `packages:` list (persists
   across restarts) or `apk add age`.
4. Test: `GH_REPO=YOUR_USER/ha-config /config/.git-sync/bin/backup_offsite.sh`

## §5. Optional: an age mirror of secrets.yaml (echelon 3)
To make the git repo self-sufficient for restoring the YAML part:
```bash
age -r "$(cat /config/.git-sync/age_recipient)" -o /config/secrets.yaml.age /config/secrets.yaml
```
`secrets.yaml.age` is NOT gitignored → it goes to git. Add the command to ha_git_sync.sh before
`git add` if you enable this. Decryption requires only the private key, which is not on HA.

## §6. Final — the mandatory first drill
Right after installation run `restore.sh full` in DRILL mode (steps 1–4). Record the date in
`/config/.git-sync/last_drill`.
