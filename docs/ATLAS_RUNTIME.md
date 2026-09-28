# Atlas runtime (what 1-click actually installs)

Researched 2026-09-28 from:

- https://hermesatlas.com/projects/NousResearch/hermes-paperclip-adapter
- https://hermesatlas.com/use-cases (14 stacks)
- https://hermesatlas.com/lists (6 lists, ~150 projects)
- https://hermesatlas.com/projects/obra/superpowers
- https://hermesatlas.com/lists/multi-agent-frameworks
- https://hermesatlas.com/projects/builderz-labs/mission-control

Machine-readable copy: `catalog/atlas.json` (synced onto the board).

## Verdict

Atlas is a catalog, not an install set. Dumping it onto a PC fights itself:

- **Two orchestrators confuse** (Atlas, multi-agent pipeline caveat). Mission Control, Minions, Agent of Empires, Swarmclaw, and Neighbourhood all want to own dispatch/review.
- **Memory is the leak.** 37 memory providers. Mem0 is already live. Adding Hindsight/Cognee/gbrain undoes the private-stack story.
- **24 GUIs + CC Switch + Hermes desktop.** User already rejected a mega-plugin that boots Hermes and owns Telegram.
- **TradingAgents** is a financial swarm, not PC ops.

So 1-click does three things:

1. **Repair the PC runtime** — Python 3.11+, git, node, uv, Hermes CLI, `hermes doctor`, Beads CLI.
2. **Install Superpowers** — the one Atlas skill that is an official `hermes plugins install`.
3. **Keep Neighbourhood as the control plane** — optional vendor flags for Paperclip adapter (npm only) and Mission Control (clone, never start `:3000`).

## Named projects

| Project | Stars | What 1-click does |
|---|---|---|
| obra/superpowers | 292k | `hermes plugins install obra/superpowers --enable --force` (scanner flags docs/tests; `--force` required) |
| NousResearch/hermes-paperclip-adapter | 1.9k | Optional `-PaperclipAdapter`. Needs a Paperclip *company* to be useful. Does not start paperclip.ing. |
| builderz-labs/mission-control | 6.3k | Gated `-MissionControl` clone only. Alpha control plane on `:3000`. Do not auto-start. |
| mem0ai/mem0 | 66k | Already have. Keep. |
| farion1231/cc-switch | 137k | Already have for models/proxy. Hub owns MCP. |
| TauricResearch/TradingAgents | 108k | Skip. |

## Gated (human go still required)

- `gt install ~/gt`, Mayor, polecats
- beads-mcp in the hub
- live `mcp.json` / `config.yaml` edits
- starting Mission Control
- standing up a Paperclip server
- extra browser MCP / extra memory provider / extra GUI

## How to run

```
Install.cmd                 full 1-click (runtime repair + board + snapshot)
Runtime.cmd                 repair Hermes + PC tools + Superpowers only
Install.cmd -PaperclipAdapter
Install.cmd -MissionControl
```

`Runtime.cmd` is the "fix this Hermes install" button. It does not curl|bash the official installer over a working tree, and it does not `hermes gateway install` (that drops cron jobs).
