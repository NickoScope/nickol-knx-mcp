# Restore runbook

## Scenario A: a broken file/config (frequent) — Circuit 1
```bash
cd /config
git log --oneline -10                 # find the last known-good commit
git diff <sha> --stat                 # what changed
git checkout <sha> -- automations.yaml   # surgical rollback
ha core check && ha core restart
```
Time: minutes. If HA won't start at all — same commands via the SSH add-on (it lives
independently of Core).

## Scenario B: dead SD/SSD/hardware — Circuit 2
1. Fresh HA OS install on the new medium.
2. On your workstation: download the latest `backup/*` release from `ha-config`, decrypt:
   `age -d -i age_key.txt -o restored.tar ha-backup-*.tar.age`
3. New HA onboarding → "Restore from backup" → upload restored.tar.
4. After start verify: entity registry intact, auth alive, dashboards present, ESPHome nodes
   reconnected, zigbee/z-wave network up.
5. Verify Circuit 1: `cd /config && git status` (the repo arrives inside the backup, .git and all).

## Scenario C: need a year-old config
Circuit 1: `git log --before="2025-07-01" -1` → checkout the needed file from that SHA.

## The monthly DRILL (1st of the month, reminder ships in automations.yaml)
The goal — prove the "Releases → age → tar" chain is alive WITHOUT a real restore:
1. Download the latest release.
2. `age -d` with the private key (this doubles as "the key isn't lost" check!).
3. `tar -tf restored.tar | grep -c .` — the archive reads.
4. `tar -tf restored.tar | grep core.config_entries` — .storage is inside.
5. `date +%F > /config/.git-sync/last_drill`
Any step failing = an incident: fix now, not when the SSD burns.

## System health metrics
- `sensor.git_sync_status` = ok, age < 26 h
- `.git-sync/last_offsite` — age < 8 days
- `.git-sync/last_drill` — age < 35 days
