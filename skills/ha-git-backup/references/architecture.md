# Architecture: design rationale

## Why two circuits, not one
Git answers "what changed and when" (diffs, blame, file rollback in seconds). A backup answers
"how do I bring the system up from nothing" (.storage: entity registry, auth, config entries,
the zigbee network). Mixing the two jobs produces a system that does both badly — the main
lesson from analysing GithubConfigSync.

## Comparison with alternatives
| Solution | History | Full recovery | Secrets | Verdict |
|---|---|---|---|---|
| **This system** | real git | Releases + age | 3 echelons | ✅ |
| GithubConfigSync | pseudo-git (Contents API, commit per file) | no (.storage excluded) | .gitignore only | history — yes, restore — no |
| Git Pull add-on (official) | pull only | no | — | a different job (deploy) |
| Google Drive Backup add-on | no | yes | HA encryption | great as an ADDITION to Circuit 2 (second offsite copy = full 3-2-1) |
| Bare cron+git | yes | no | manual | that IS Circuit 1, but without scan/notify/lock |

## Key decisions
1. **Deploy key instead of a PAT for git** — blast radius of one repo.
2. **Fine-grained PAT only for the Releases API** (Contents RW, one repo) — Releases can't be
   pushed over SSH.
3. **The pre-commit scan is mandatory**: .gitignore does not protect against a secret written
   INTO automations.yaml as a literal (a real, frequent case: a Telegram bot token in a
   rest_command).
4. **Whitelist `.storage/lovelace*`**: dashboards created in the UI live in .storage — without
   them the config history is incomplete. The rest of .storage holds auth → encrypted Circuit 2
   only.
5. **age, not GPG**: a single binary, no keyring state, the key is one line. There is NO private
   key on the HA host — a compromised host ≠ readable backups.
6. **GitHub Releases, not git-lfs and not files in the repo**: binaries in git bloat history
   forever; Releases is flat storage with a 2 GB/file limit and trivial rotation.
7. **A status file + command_line sensor, not push notifications from the script**: the script
   does not depend on HA API tokens; observability is done by HA itself.
8. **Locking via flock**: an HA restart plus the daily trigger cannot race.

## System boundaries (deliberate)
- The 2 GB Releases limit: exclude media/large DBs from the native backup (partial backup).
- The git repo in /config is visible to every add-on with config access — threat model:
  trusted add-ons.
- Git history keeps deleted files forever: a leaked secret requires the
  incident-secret-leak.md protocol, not a simple delete.
