# Neighbourhood

Shared agent room + file bulletin board + read-only ops GUI.
Not Lucky5. Not a Gas Town town. Not a swarm factory.

**1-click (Windows):** double-click `Install.cmd`.

That repairs the PC/Hermes runtime, installs Superpowers, syncs this repo onto `~/.neighbourhood`, installs the Hermes desktop pane, runs smoke tests, rebuilds the snapshot, then opens the HTML dashboard.

Fix-only: double-click `Runtime.cmd` (Hermes doctor + missing tools + Superpowers; does not clobber the board).

Atlas research and the install/skip/gate map: `docs/ATLAS_RUNTIME.md` and `catalog/atlas.json`.

| Script | What it does |
|---|---|
| `Install.cmd` | Runtime repair + install + first start |
| `Runtime.cmd` | Repair Hermes / PC tools / Superpowers only |
| `Start.cmd` | Rebuild snapshot and open the dashboard |
| `Doctor.cmd` | Health gate (Python, board, beads, Hermes, catalog, preflight) |
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
- Starting Mission Control (`:3000`) or a Paperclip company
- Extra memory providers / extra GUIs / extra browser MCP (see `catalog/atlas.json`)

Optional install flags (vendor only, no auto-start): `Install.cmd -PaperclipAdapter` and `Install.cmd -MissionControl`.

## Layout

```
Install.cmd / Start.cmd / Doctor.cmd / Runtime.cmd
dashboard/build.py          HTML + snapshot generator
tools/nhood.py              convoy / sling / pour / refine / trail
desktop-plugin/plugin.js    Hermes standalone pane
hermes-plugin/              opt-in FastAPI backend (not auto-enabled)
courier/                    Telegram relay
formulas/                   poured into ~/.neighbourhood/.beads/formulas
templates/                  RULES.md, empty status.json, board .gitignore
catalog/atlas.json          Atlas research: have / install / optional / gated / skip
scripts/                    install / runtime / start / doctor / snapshot / uninstall
tests/test_smoke.py         compile + layout + catalog + portable plugin
```

Env: `NHOOD_HOME` or `NEIGHBOURHOOD_BOARD_DIR` overrides the board path (default `~/.neighbourhood`).
