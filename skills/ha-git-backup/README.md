# ha-git-backup — the ops companion skill

Our Scenario 3 ends with `generate_ha_package` handing you a Home Assistant KNX YAML. This
skill covers what happens **after you deploy it**: the life of your `/config`.

**Two circuits, two different jobs:**

1. **History** — a *real* git repo inside `/config`, pushed to a private GitHub repo over a
   **deploy key** (blast radius: one repo). Every change is a meaningful commit
   (`[daily] 3 file(s) | HA 2026.7.1`); a **pre-commit secret scanner** blocks any commit whose
   diff contains a token, password or private key. Answers "what broke my automation last night"
   in one `git diff`.
2. **Recovery** — full native HA backups (including `.storage`: entity registry, auth, UI
   dashboards) **age-encrypted** and uploaded to GitHub Releases with rotation. The private age
   key never touches the HA host — a compromised host cannot read its own backups. Answers
   "the SSD died" with a 30-minute restore.

Plus: HA automations (daily commit at 03:30, a pre-update tag, a sync button, a failure alert),
a health sensor, a restore runbook and a **mandatory monthly restore drill** — because a backup
you have never restored is a hypothesis, not a backup.

## Quick start

```text
1. Create an empty PRIVATE GitHub repo (e.g. ha-config).
2. Follow references/setup.md: deploy key → scripts to /config/.git-sync/bin → install.sh.
3. Add assets/configuration_snippet.yaml + assets/automations.yaml, restart HA (full restart).
4. Circuit 2: age key + fine-grained PAT (Contents RW, ONE repo) → backup_offsite.sh.
5. Run the first restore drill immediately (references/restore-runbook.md).
```

Start with [SKILL.md](SKILL.md) — it is written as a Claude skill (drop it into
`.claude/skills/` and Claude will walk you through installation, incidents and drills), but it
reads just as well as plain documentation for humans.

> Field-tested: the secret scanner ships canary-tested (see LESSON-05 — a BusyBox grep quirk
> silently disabled the private-key pattern until a planted-secret test caught it).
