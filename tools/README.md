# Neighbourhood Gas Town lite

Steal **convoy / sling / formula / trail** from Gas Town without installing a town.

```
python tools/nhood.py convoy create "Title" --tracks nhood-xxx,nhood-yyy
python tools/nhood.py sling nhood-xxx --to backend-engineer --summary "..."
python tools/nhood.py pour nhood-feature --var feature=foo [--parent nhood-5xu]
python tools/nhood.py trail
python dashboard/build.py          # pulls snapshot-layer into the pane
```

- Beads is the data plane (`-t convoy` + `bd dep add -t tracks`).
- Sling writes a handoff and sets assignee. It does **not** `hermes kanban --assignee` (that spawns).
- `gt formula run` is off-limits here (polecats). Pour with this CLI.
- Still gated: `gt install ~/gt`, Mayor, polecats, beads-mcp.
