# Codex orch GUI — steal list (do not revive wholesale)

Source: `D:/Users/kapo_/Documents/github/codex-orch-unified`
Primary surfaces: `app/page.tsx`, `app/components/dashboard/shell/*`, `lib/cockpit/dashboard-state.ts`
Plan: `docs/plans/2026-03-27-atoms-style-parallel-dashboard-redesign.md`

## Steal (UX + contracts)

1. **Five-zone workbench, not one long page**
   - Top command bar (identity, health, last heartbeat, primary controls)
   - Center canvas (the thing you stare at)
   - Left rail (pane switcher: agents / board / probes / memory / settings)
   - Right inspector (detail of the selected agent/handoff/server)
   - Bottom telemetry dock (events, probes, history)
2. **Preflight gate before action** — control-center pattern: blocking issues vs warnings, never start a run/sync when setup is red.
3. **File-backed state + poll/SSE** — dashboard reads JSON on disk (`status.json`, `handoffs/`, `health.json`). No extra database.
4. **Provider/tool inventory chips** — connection state, source of truth, whether it blocks work.
5. **Workspace-aware** — every probe and action is scoped to a selected root (here: `~/.mcp-hub` vs `~/.neighbourhood` vs Lucky5). Never silently use `cwd`.
6. **Kanban as a pane, not the whole product** — `app/components/dashboard/kanban/KanbanBoard.tsx`.

## Do not steal

- Swarm pause/resume/rewind/control-queue (we are not running factory swarms unless the human asks).
- Next.js + Tailwind app shell, Qdrant-on-every-edit, Antigravity/pentest panels.
- Inline provider auth forms that would put keys in the dashboard.
- Graph executor / ADK runtime.

## Gas Town steal (lite — no town)

Source: `gt` 1.2.1 + Beads 1.3.0. **Do not** `gt install ~/gt`, Mayor, polecats, or beads-mcp.

| Gas Town | Neighbourhood lite |
|---|---|
| Convoy | `bd create -t convoy` + `bd dep add -t tracks`. CLI: `python tools/nhood.py convoy …` |
| Sling | assignee + write-once handoff. **Never** `hermes kanban --assignee` (spawns) |
| Formula | `.beads/formulas/*.toml`. Pour with `nhood.py pour` — not `gt formula run` |
| Trail | git + handoffs + beads, bottom telemetry dock |
| Witness | stale-heartbeat banner (45m) in snapshot |

## Neighbourhood v1 mapping

| Codex zone | Neighbourhood v1 |
|---|---|
| Command bar | snapshot time, MCP verified pass/fail, unread handoffs |
| Center canvas | handoff feed |
| Left rail | agent heartbeats |
| Right inspector | selected handoff / MCP server detail |
| Telemetry dock | last healthcheck stanza + path-tool list |
| Control-center | Kimi's `scripts/preflight.ps1` (env/path) — not this dashboard |
