# Architecture

Two homes:

| Home | Role |
|---|---|
| This repo (`Documents/github/Neighbourhood`) | Product: dashboard, nhood CLI, plugins, 1-click scripts |
| `~/.neighbourhood` | Instance: status, handoffs, beads DB, generated snapshot |

`Install.cmd` runs runtime repair first (`scripts/runtime.ps1`: Python/git/node/uv, Hermes doctor, Beads CLI, Superpowers plugin), then copies product → instance (refreshing code, seeding templates only when missing) and installs:

- `%LOCALAPPDATA%/hermes/desktop-plugins/neighbourhood/plugin.js` (loads by default)
- `%LOCALAPPDATA%/hermes/plugins/neighbourhood/` (FastAPI `plugin_api.py` — **not** added to `plugins.enabled`)
- Superpowers via `hermes plugins install obra/superpowers --enable` (not a config.yaml edit)
- `~/.neighbourhood/catalog/atlas.json` (Atlas have/install/optional/gated/skip map)

`Runtime.cmd` is the fix-only button. It does not curl|bash over a live Hermes tree and does not `hermes gateway install` (that drops cron).

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

Gas Town town (`gt install ~/gt`), Mayor, polecats, beads-mcp, hub `mcp.json` edits, starting Mission Control on `:3000`, standing up a Paperclip company. Atlas dump-install of extra GUIs / memory providers / swarms is a skip — see `catalog/atlas.json`.
