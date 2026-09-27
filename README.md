# Neighbourhood

Shared agent room + file bulletin board + read-only ops GUI.
Not Lucky5. Not a Gas Town town. Not a swarm factory.

**1-click (Windows):** double-click `Install.cmd`.

That syncs this repo onto `~/.neighbourhood`, installs the Hermes desktop pane, runs smoke tests, rebuilds the snapshot, then opens the HTML dashboard.

| Script | What it does |
|---|---|
| `Install.cmd` | Install + first start |
| `Start.cmd` | Rebuild snapshot and open the dashboard |
| `Doctor.cmd` | Health gate (Python, board, beads, preflight) |
| `scripts/snapshot.ps1` | Rebuild snapshot only |
| `scripts/uninstall.ps1` | Remove plugins; pass `-WipeBoard` to delete `~/.neighbourhood` |

## What you get

- **File board** — `~/.neighbourhood/status.json` + `handoffs/` + `RULES.md` (coordination source of truth)
- **HTML dashboard** — `python dashboard/build.py` → `dashboard/index.html`
- **Hermes desktop pane** — sidebar **Neighbourhood**, status-bar **Nhood**, palette **Open Neighbourhood**
- **Gastown-lite** — `python tools/nhood.py convoy|sling|pour|refine|trail` (no Mayor, no polecats)
- **Beads DAG** — prefix `nhood`, embedded Dolt, in the board repo
- **Telegram courier** — `courier/neighbourhood_courier.py` (dry-run until `courier-config.json`)

Live instance data (handoffs, beads DB, heartbeats) stays on the board. This GitHub repo is the product.

## After install

1. Hermes desktop: **⌘K → Reload desktop plugins** if the pane is missing.
2. Optional Beads CLI: `npm install -g @beads/bd` then re-run `Install.cmd`.
3. Courier: copy `courier/courier-config.example.json` → `courier-config.json` next to the script (never commit it). Prefer a Hermes `--no-agent` cron over a second bot.

```
python ~/.neighbourhood/tools/nhood.py convoy create "Title" --tracks nhood-xxx
python ~/.neighbourhood/tools/nhood.py sling nhood-xxx --to backend-engineer --summary "…"
python ~/.neighbourhood/tools/nhood.py pour nhood-feature --var feature=foo
python ~/.neighbourhood/tools/nhood.py refine --dry-run
python ~/.neighbourhood/dashboard/build.py
```

## Gated (do not run unless the human says go)

- `gt install ~/gt`
- Mayor / polecats
- beads-mcp in the MCP hub
- `hermes kanban --assignee` (that **spawns** a live roommate)
- Editing `~/.mcp-hub/mcp.json` or live `config.yaml`

## Layout

```
Install.cmd / Start.cmd / Doctor.cmd
dashboard/build.py          HTML + snapshot generator
tools/nhood.py              convoy / sling / pour / refine / trail
desktop-plugin/plugin.js    Hermes standalone pane
hermes-plugin/              opt-in FastAPI backend (not auto-enabled)
courier/                    Telegram relay
formulas/                   poured into ~/.neighbourhood/.beads/formulas
templates/                  RULES.md, empty status.json, board .gitignore
scripts/                    install / start / doctor / snapshot / uninstall
tests/test_smoke.py         compile + layout + portable plugin
```

Env: `NHOOD_HOME` or `NEIGHBOURHOOD_BOARD_DIR` overrides the board path (default `~/.neighbourhood`).
