# Neighbourhood agent contract

PC-wide ops board. Not Lucky5. Not a swarm factory.

## Source of truth

- File board (`~/.neighbourhood/status.json` + `handoffs/` + `RULES.md`) is coordination SoT.
- This GitHub repo is the **product**. Install.cmd copies code onto the board; it must not clobber live handoffs or `status.json`.
- Hermes kanban board `neighbourhood` is dispatcher. Lucky5 stays on kanban `default`.
- Beads (`bd`, prefix `nhood`) is the work DAG in the board repo.

## Do

- Update only your own `status.json` agent entry. Handoffs are write-once.
- Sling with `python tools/nhood.py sling` — never `hermes kanban --assignee`.
- Rebuild the snapshot after posting a handoff (`python dashboard/build.py`, twice if the pane should show the new card).
- Keep secrets out of the board and out of this repo (`courier-config.json` is gitignored).

## Do not

- `gt install ~/gt`, Mayor, polecats, or beads-mcp unless the human says go.
- Start Mission Control or a Paperclip company from 1-click (vendor flags clone/npm only).
- Dump-install Atlas lists (extra GUIs, extra memory providers, TradingAgents).
- Auto-dispatch a live roommate. Leave cards unassigned or blocked while that profile is in the room.
- Steal a claimed bead (`bd update --claim` errors if another actor holds it).
- Edit `mcp.json` / live `config.yaml` without a hub plan + go.
- `bd init` in Lucky5.
- Ship `plugins/neighbourhood/desktop/plugin.js` while a marker-less standalone already exists under `desktop-plugins/neighbourhood/`.

## Pitfalls

- **`HERMES_HOME` is not always the app root.** A Hermes session may export it profile-scoped (`<root>/profiles/<name>`). `Get-HermesHome` in `scripts/common.ps1` must walk up until a directory owns `desktop-plugins\`. Trusting `$env:HERMES_HOME` verbatim makes Doctor/install look under the profile dir and false-FAIL `plugin.js` even when the pane is at `%LOCALAPPDATA%/hermes/desktop-plugins/neighbourhood/`. Doctor accepts either the standalone pane or `plugins/neighbourhood/desktop/plugin.js`.

## Verify

```
Doctor.cmd
Runtime.cmd
python tests/test_smoke.py
python dashboard/build.py
```
