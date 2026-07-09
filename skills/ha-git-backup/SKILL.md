---
name: ha-git-backup
description: >-
  Two-circuit backup & GitHub sync system for Home Assistant. Circuit 1 — real git inside
  /config with a deploy key, a pre-commit secret scanner and meaningful commits; Circuit 2 —
  full encrypted HA backups in GitHub Releases. Use EVERY time the task involves: backing up
  Home Assistant, syncing its config, git in /config, restoring a config, rolling back a YAML
  change, "what broke my automation", a leaked secret, setting up a deploy key, migrating HA
  to new hardware, GitHub Releases for backups — and BEFORE any HA Core/OS update or AFTER any
  incident with config loss. Also trigger on: backup, restore, gitleaks, secrets.yaml, 3-2-1.
  The skill ships ready-made scripts (install, sync, secret-scan, offsite, restore) and a
  mandatory protocol — do NOT reinvent sync logic, use scripts/.
---

# HA Git Backup — a two-circuit system

Philosophy: **git gives you history, a backup gives you recovery. These are different jobs —
different circuits solve them.** Projects like GithubConfigSync mix the two and implement git
on top of the Contents API — we use real git.

## Architecture

```
CIRCUIT 1: CONFIG HISTORY (what changed and when)
/config (git repo) ──deploy key──▶ GitHub private repo (ha-config)
  ├── triggers: daily 03:30 / pre-update / button / HA restart
  ├── secret protection: .gitignore → pre-commit scan → age mirror
  └── commit: "[trigger] N files | HA 2026.7.1" + file list

CIRCUIT 2: RECOVERY (full state, including .storage)
HA native backup (.tar) ──age──▶ GitHub Releases (ha-config)
  ├── schedule: weekly + before updates
  ├── rotation: 8 releases
  └── restore drill: 1st of the month (mandatory)
```

The 3-2-1 rule: the config lives (1) on the HA host, (2) in the GitHub git repo, (3) as a full
tarball in Releases — plus a local NAS copy if you have one.

## IRON RULES

1. **Deploy key, not a PAT.** Fine-grained WRITE access to ONE repository. A classic token with
   the `repo` scope = access to all your private repos → forbidden.
2. **A secret in the diff blocks the commit.** The pre-commit hook runs `secret_scan.sh`.
   Bypassing with `--no-verify` — only deliberately, with the reason logged.
3. **`.storage/` does NOT go to git** (auth, tokens), except the `lovelace*` whitelist —
   dashboards. The full `.storage` lives only in the encrypted Circuit-2 tarball.
4. **A backup without a restore drill is not a backup.** Monthly: download the release →
   `age -d` → `tar -t` → verify `.storage/core.config_entries` is inside.
5. **Do not rewrite the scripts from scratch.** The logic (lock, retry, notify, rotation) is
   already in `scripts/` — read and use them.

## Quick start (fresh install)

1. Create an empty private repo `ha-config` on GitHub.
2. Read `references/setup.md` — step by step: deploy key, install via the SSH add-on.
3. Run `scripts/install.sh` inside HA — it does git init, .gitignore, hook, remote, first dry-run.
4. Add the contents of `assets/configuration_snippet.yaml` to configuration.yaml and
   `assets/automations.yaml` to your automations. **A full HA restart is required**
   (`shell_command` and `command_line` are NOT loaded by a quick reload).
5. Circuit 2: `scripts/backup_offsite.sh` needs a fine-grained PAT + an age key.
   See `references/setup.md` §4.
6. Run the first restore drill IMMEDIATELY — before the system is ever needed.

## Symptom → action map

| Symptom | Action |
|---|---|
| "Worked yesterday, broken today" | `git log --oneline -10`, `git diff HEAD~1` in /config — see what changed |
| Broke YAML, HA won't start | `git checkout -- <file>` or `git reset --hard <good_sha>`, restart |
| Secret leaked into the repo | `references/incident-secret-leak.md` — rotate the secret FIRST, history second |
| Push silent/failing | `/config/.git-sync/log`; typical: read-only deploy key, stale known_hosts |
| Nightly commit is local but never on GitHub (`Host key verification failed` in the log) | `shell_command` runs from the Core container — pin `git config core.sshCommand` with a repo-local known_hosts (see LESSON-06); install.sh does this automatically |
| Migrating to new hardware | `scripts/restore.sh` — the Circuit-2 tarball, NOT the git repo (git has no .storage) |
| Sync sensor = error | Check the log; the automation already sends a persistent_notification |
| Repo bloated | Check binaries (db, tar) are gitignored; history is cleaned with `git gc` |

## What's in the skill

- `scripts/install.sh` — bootstrap the git repo in /config
- `scripts/ha_git_sync.sh` — the sync engine: lock → scan → commit → push with retry → status file
- `scripts/secret_scan.sh` — diff-based secret scanner (keys, tokens, private keys, passwords not via !secret)
- `scripts/backup_offsite.sh` — Circuit 2: age encryption + upload to GitHub Releases + rotation
- `scripts/restore.sh` — interactive restore with a checklist
- `assets/gitignore.template`, `assets/configuration_snippet.yaml`, `assets/automations.yaml`
- `references/setup.md` — full installation from scratch (deploy key, age, PAT)
- `references/architecture.md` — design rationale, comparison with alternatives
- `references/incident-secret-leak.md` — the secret-leak incident protocol
- `references/restore-runbook.md` — restore runbook and the monthly drill

## LESSONS (recorded — do not repeat)

- **LESSON-01**: the GithubConfigSync approach (files one by one via the Contents API) = a commit
  per file, rate limits, snapshot duplicates in the git repo. Real git solves all of that for free.
- **LESSON-02**: .gitignore is NOT protection. A file added before the rule keeps being tracked.
  Hence the mandatory pre-commit scan.
- **LESSON-03**: a config git repo ≠ a backup: without .storage a restore gives you a bare HA
  with no entity registry, no auth, no UI dashboards.
- **LESSON-04**: a restore drill in calm times costs 10 minutes. A first-ever restore during an
  outage without a drill costs an evening and your nerves.
- **LESSON-05**: BusyBox grep treats patterns starting with `-` as options — always pass scan
  patterns with `grep -E -e "$pattern"`. The scanner was silently skipping its private-key
  pattern until this was caught by a canary test. Test your scanner with planted secrets.
- **LESSON-06**: HA `shell_command` (the nightly sync) runs in the **Core** container, not the
  SSH add-on where install ran. Core has its own empty known_hosts → `git push` fails
  `Host key verification failed` even though the deploy key is fine — the commit is made locally
  but never reaches GitHub. The fix: pin `git config core.sshCommand` (the key + a repo-local
  known_hosts + `accept-new`) into `.git/config` so it applies from ANY container. install.sh
  does this automatically. Testing SSH from the add-on alone is not enough — it never exercises
  the container the sync actually runs in.
