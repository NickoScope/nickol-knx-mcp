# Incident: a secret landed in the git repo

The order is STRICT. Step 1 comes before everything else.

## 1. ROTATE THE SECRET (immediately)
A leaked token/password/key counts as compromised from the moment of push, even in a private
repo. Revoke and reissue it at the provider (GitHub token → revoke; a service API key →
regenerate; a password → change). Only then move on to cleanup.

## 2. Assess the exposure
- `git log --all -S '<secret fragment>' --oneline` — which commits carry it.
- Is the repo private? Any forks/clones? Who had access?

## 3. Rewrite history
```bash
# on your workstation, not on HA:
git clone git@github.com:YOUR_USER/ha-config.git && cd ha-config
pip install git-filter-repo
git filter-repo --replace-text <(echo '<secret>==>REDACTED')
git push --force --all && git push --force --tags
```
On HA afterwards: `cd /config && git fetch && git reset --hard origin/main`.

## 4. GitHub specifics
A force-push does NOT delete objects instantly: commits stay reachable by SHA via cache/API.
For a full purge — GitHub Support (a request to delete unreachable objects). One more reason
step 1 is primary: history may never be fully scrubbed; rotation closes the risk with certainty.

## 5. Close the gap
- Why didn't the scan catch it? → add the pattern to `secret_scan.sh` PATTERNS.
- The value should have lived in secrets.yaml behind `!secret` — move it.
- Record a LESSON in SKILL.md.
