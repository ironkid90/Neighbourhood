# Neighbourhood Rules

Shared space for all agents + the Telegram courier. Keep it friendly and functional.

1. **status.json** — update ONLY your own entry (`neighbourhood_set_status` with your agent name). Never edit another agent's entry.
2. **handoffs/** — write-once. Never modify a handoff after creation; post a new one for updates (`neighbourhood_post_handoff`).
3. Mark handoffs read with `neighbourhood_mark_read` after acting on them.
4. All timestamps are ISO 8601 UTC. All JSON must be valid and parseable.
5. Post durable outcomes to context memory (`submit_memory_summary`) — the board is for coordination, memory is for knowledge.
6. No agent starts the swarm factory (multi-round orchestration) unless the human explicitly asks.
7. When the human is away, the telegram-courier relays handoffs addressed to `human` and posts the human's replies back.
8. **Beads** (`bd`, prefix `nhood`) is the git-backed work DAG in this directory. File board stays coordination; Hermes kanban `neighbourhood` stays dispatcher. Do not `gt install ~/gt`, Mayor, polecats, or beads-mcp unless the human says go. Lucky5 stays on kanban `default` — never `bd init` there.
9. **Gastown-lite** (`python tools/nhood.py`) may convoy/sling/pour/trail on this board. Sling writes a handoff and may set a bead assignee; it must not dispatch a live roommate. `gt formula run` is off-limits (polecats). `gt convoy` needs a town — use `nhood.py convoy` instead.
