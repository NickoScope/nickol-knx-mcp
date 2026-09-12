# Release checklist

Every release ships in three places that must stay in lockstep: **git** (tag + GitHub Release),
**PyPI** (the artifact) and the **official MCP Registry** (metadata pointing at that artifact).
Skipping the third one leaves the registry advertising an older version.

Verified end to end on 2026-09-12 (0.8.0 → 0.8.1).

## 0. Before you start

- Working tree clean, CI green, `CHANGELOG.md` section for the new version written.
- Decide the version (SemVer). New user-facing features → minor bump.

## 1. Bump the version in three files

```
pyproject.toml            version = "X.Y.Z"
nickol_knx_mcp/__init__.py  __version__ = "X.Y.Z"
server.json               "version" AND "packages"[0]."version"
```

`server.json` carries the version twice. The registry rejects a publish whose package version
does not exist on PyPI, so both must match the artifact you are about to upload.

## 2. Build and check

```bash
rm -rf dist build *.egg-info
uv build --out-dir dist .
uvx twine check dist/*
```

Both artifacts must say PASSED.

## 3. Upload to PyPI (owner, needs the API token)

```bash
TWINE_USERNAME=__token__ uvx twine upload dist/nickol_knx_mcp-X.Y.Z*
```

Token lives in 1Password. **A version can never be re-uploaded** — a mistake in the package
metadata costs a new patch version, so verify step 4 *before* uploading when possible.

## 4. Ownership marker (check before uploading)

The registry proves ownership of a PyPI package by finding this exact line in the package
description, i.e. in `README.md`:

```
<!-- mcp-name: io.github.NickoScope/nickol-knx-mcp -->
```

- The name is **case-sensitive** and must equal `name` in `server.json` character for character.
  GitHub auth grants `io.github.NickoScope/*` — lowercase `nickoscope` is rejected with 403.
- Verify it survived into the built artifact before uploading:

```bash
python -c "import zipfile;z=zipfile.ZipFile('dist/nickol_knx_mcp-X.Y.Z-py3-none-any.whl');\
print('mcp-name: io.github.NickoScope/nickol-knx-mcp' in z.read([n for n in z.namelist() if n.endswith('METADATA')][0]).decode())"
```

## 5. Publish to the official MCP Registry

```bash
mcp-publisher validate          # schema + field limits
mcp-publisher login github      # device flow in the browser, owner action; token cached in ~/.config/mcp-publisher
mcp-publisher publish
```

Confirm:

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=nickol" | python3 -m json.tool | head -30
```

Expect `"status": "active"` and the new version.

## 6. Git side

Tag, GitHub Release, submodule pointer bump in the workspace repo. Per the standing rule this
part is delegated to the `github-manager` agent (version / CHANGELOG / tag / release / PII scan).

## Field limits and traps (hit for real)

| Trap | Symptom | Fix |
|---|---|---|
| `description` in `server.json` over 100 chars | `422 expected length <= 100` on `validate` | shorten; the long text stays in the README |
| server name in the wrong case | `403 You have permission to publish: io.github.NickoScope/*` | match the GitHub login exactly |
| marker in the published description in the wrong case | `400 … must appear as 'mcp-name: …' in the package README` | fix README, bump patch version, re-upload (PyPI forbids overwriting) |
| PyPI JSON API lags a few minutes | `latest` still shows the old version | check `https://pypi.org/simple/nickol-knx-mcp/` instead |

## Downstream

PulseMCP ingests from the official registry automatically (their manual submission has been
paused since mid-2026). mcp.so is paid-only since 2026 and is deliberately skipped.
awesome-mcp-servers already lists the project; only description edits are needed there.
