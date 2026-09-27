# Architecture

Two homes:

| Home | Role |
|---|---|
| This repo (`Documents/github/Neighbourhood`) | Product: dashboard, nhood CLI, plugins, 1-click scripts |
| `~/.neighbourhood` | Instance: status, handoffs, beads DB, generated snapshot |

`Install.cmd` copies product → instance (refreshing code, seeding templates only when missing) and installs:

- `%LOCALAPPDATA%/hermes/desktop-plugins/neighbourhood/plugin.js` (loads by default)
- `%LOCALAPPDATA%/hermes/plugins/neighbourhood/` (FastAPI `plugin_api.py` — **not** added to `plugins.enabled`)

## Layers

```
file board     coordination (status + write-once handoffs)
kanban nhood   dispatcher (do not assignee-spawn from sling)
beads          git-backed DAG (prefix nhood, embedded Dolt)
nhood.py       Gastown-lite: convoy / sling / pour / refine / trail
dashboard      read-only HTML + snapshot.json for the desktop pane
courier        Telegram relay of to_agent=human (dry-run without config)
```

## Path resolution

`NHOOD_HOME` / `NEIGHBOURHOOD_BOARD_DIR` override `~/.neighbourhood` in `nhood.py`, `build.py`, courier, and the install scripts.

The desktop plugin no longer hardcodes a user path. It opens `index.html` from `snapshot.board`.

## Gated

Gas Town town (`gt install ~/gt`), Mayor, polecats, beads-mcp, hub `mcp.json` edits.
