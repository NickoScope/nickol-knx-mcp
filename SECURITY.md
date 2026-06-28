# Security Policy

## The safety model

`nickol-knx-mcp` is a **design-time** tool with a deliberately small attack surface:

- **No bus access.** There is no KNX/IP or other networking/bus library in the dependency tree.
  The server cannot reach a live KNX installation. `workspace_info()` reports `bus_access: false`.
- **Read-only on `.knxproj`.** Only `project.py` reads the project, and it never writes to it.
- **Confined writes.** All generated files are constrained to the `NICKOL_KNX_WORKSPACE` directory;
  writes outside it are rejected.

## Handling project data

A `.knxproj` and an ETS keyring (`.knxkeys`) can contain sensitive information (topology, device
addresses, secure keys). This tool reads the project locally and writes only into your workspace —
nothing is uploaded anywhere. **Do not commit real `.knxproj` / `.knxkeys` files** to a public
repository; the provided `.gitignore` excludes them by default.

## Reporting a vulnerability

If you find a security issue (e.g. a path-escape past the workspace confinement, or any way the
server could touch a bus), please **do not open a public issue**. Instead use GitHub's
[private vulnerability reporting](https://github.com/NickoScope/nickol-knx-mcp/security/advisories/new)
for this repository. We'll acknowledge within a reasonable time and coordinate a fix and disclosure.

## Supported versions

This is a beta; security fixes target the latest `main` and the most recent release.
