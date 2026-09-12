# Contributing to nickol-knx-mcp

Thanks for helping! This project is in **public beta**, and the single most valuable contribution
right now is **testing against real ETS projects**.

## 🧪 The #1 ask: test on your real `.knxproj`

The tool is **read-only and never connects to a KNX bus**, so running it against a production
project is safe. Here is the fastest way to help:

```bash
git clone https://github.com/NickoScope/nickol-knx-mcp.git
cd nickol-knx-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/test_pipeline.py        # should pass
```

Then run it from Claude (Desktop or Code) and ask it to:

1. `load_project` your `.knxproj` (with the ETS password if it's protected),
2. `analyze_all`, and
3. `project_report`.

Open a **[Real-project test report](https://github.com/NickoScope/nickol-knx-mcp/issues/new?template=real_project_test.yml)**
issue and tell us:

- ETS version (5 / 6) and roughly how many group addresses / devices,
- what the report got **right**,
- what it got **wrong** (false missing-status, wrong category, wrong DPT call, bad HA YAML),
- any crash or stack trace.

**Please do not attach your actual `.knxproj`** (it can contain personal/topology data). A redacted
snippet or a screenshot of the report is plenty. If a parse crash needs a sample, we'll coordinate a
minimal redacted project privately.

## 🐛 Bugs & 💡 features

Use the [issue templates](.github/ISSUE_TEMPLATE). For bugs, include OS, Python version, the exact
tool call, and the full error.

## 🔧 Code contributions

- Keep the **safety invariant**: `project.py` is the only module allowed to read `.knxproj`, and it
  must stay read-only. No networking / bus libraries may enter the dependency tree.
- Keep generators **conservative**: when in doubt, push an item to the `review` list rather than
  emitting a guessed entity.
- Run the smoke test before opening a PR:
  ```bash
  python tests/test_pipeline.py
  ```
- Match the existing module boundaries (one responsibility per file) and naming style.
- New classification rules should be backed by a case in `tests/test_pipeline.py`.

## Dev setup

```bash
pip install -e .
python tests/test_pipeline.py
```

CI runs the smoke test on Python 3.10–3.12 for every push and PR.

### Local corpus guard

Public CI only sees the synthetic fixtures in `tests/`. Most real regressions show up on real
ETS projects, which are confidential and never leave the maintainer's machine. `tools/corpus_check.py`
closes that gap locally: it runs every project of a private corpus through the full pipeline
(parse -> checks -> HA YAML -> entity suggestions) and compares the resulting counts against a
recorded baseline.

```bash
cp tools/corpus_map.example.json tools/corpus_map.json   # once: point it at local .knxproj files
python tools/corpus_check.py              # exits 1 and prints every metric that moved
python tools/corpus_check.py --tolerance 2  # allow 2% drift per metric
python tools/corpus_check.py --update       # re-record the baseline after an intended change
```

`tools/corpus_map.json` is gitignored, because real project paths carry client names. The corpus
root defaults to a sibling `demo-home-for-friend/` directory and can be overridden with
`NICKOL_KNX_CORPUS_DIR`. Without a map the script exits 2 and does nothing.

`tools/corpus_baseline.json` is committed, but it holds numbers only: counts, severity and code
histograms, and a short digest of each source file. No project names, no paths, no addresses.
The corpus itself stays out of the repository. Contributors without the corpus can skip this
step; the maintainer runs it before every release, and `--update` belongs in the same commit as
the change that moved the numbers, so the diff shows what moved and why.

## Code of conduct

Be kind and constructive. This is a hobby/community project; assume good faith.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).

## Releasing

See [docs/RELEASE.md](docs/RELEASE.md) — version bump in three files (`pyproject.toml`,
`nickol_knx_mcp/__init__.py`, `server.json` twice), PyPI upload, and a publish to the official
MCP Registry. The registry's ownership check is case-sensitive and a PyPI version can never be
re-uploaded, so the checklist is worth following literally.
