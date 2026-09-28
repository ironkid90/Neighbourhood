#!/usr/bin/env python3
"""Neighbourhood smart router: classify a task, pick the best-suited agent,
and route it with full context.

Design principles:
- Read-mostly: agents declare capabilities in status.json; router never edits
  another agent's entry, only posts write-once handoffs.
- Degrades gracefully: if capabilities aren't declared, falls back to name
  matching; if beads is down, still posts the handoff (coordination survives).
- Observable: every routing decision is a handoff + optional bead, so the
  dashboard and audit trail show who got what and why.

Usage:
    python tools/router.py "fix the login form CSS" --dry-run
    python tools/router.py "add REST endpoint for payments" --post
    python tools/router.py --update-capabilities  # self-declare from template
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse nhood.py's board discovery
def board_dir() -> Path:
    return Path(
        os.environ.get("NHOOD_HOME")
        or os.environ.get("NEIGHBOURHOOD_BOARD_DIR")
        or (Path.home() / ".neighbourhood")
    )

BOARD = board_dir()
STATUS = BOARD / "status.json"
HANDOFFS = BOARD / "handoffs"
ACTOR = os.environ.get("NHOOD_AGENT") or "router"

# --- Capability taxonomy -------------------------------------------------
# Maps capability tags to the kinds of work they cover. Agents declare these
# in status.json; the router matches task keywords against them.

CAPABILITY_TAGS = {
    "frontend": ["ui", "css", "html", "dom", "react", "vue", "svelte", "frontend", "page", "component", "form", "button", "layout", "界面", "样式", "页面"],
    "backend": ["api", "endpoint", "rest", "server", "database", "backend", "auth", "upload", "handler", "后端", "接口"],
    "database": ["sql", "schema", "migration", "query", "db", "database", "table", "index", "数据", "数据库"],
    "debug": ["bug", "error", "crash", "debug", "fix", "broken", "issue", "调试", "错误"],
    "review": ["review", "audit", "check", "inspect", "代码审查"],
    "docs": ["document", "readme", "guide", "tutorial", "docs", "documentation", "文档"],
    "test": ["test", "spec", "coverage", "测试"],
    "devops": ["deploy", "ci", "cd", "docker", "kubernetes", "运维"],
    "design": ["design", "architecture", "spec", "diagram", "设计"],
    "api-design": ["api", "endpoint", "contract", "openapi", "接口"],
}

# Default capability hints for known agent names (fallback when not declared)
NAME_HINTS = {
    "frontend-engineer": ["frontend", "ui"],
    "backend-engineer": ["backend", "api", "database"],
    "architect": ["design", "api-design"],
    "api-designer": ["api-design", "design"],
    "code-reviewer": ["review"],
    "debugger": ["debug"],
    "doc-writer": ["docs"],
    "hermes": ["router", "coordinator"],
    "telegram-courier": ["courier", "notify"],
}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_status() -> dict:
    if not STATUS.exists():
        return {"agents": {}}
    return json.loads(STATUS.read_text(encoding="utf-8"))


def get_agent_capabilities(agent_name: str, agent_data: dict) -> list[str]:
    """Extract capability tags from status.json, falling back to name hints."""
    # Explicit declaration wins
    caps = agent_data.get("capabilities", [])
    if caps:
        return [c.lower() for c in caps]
    # Fallback to name-based hints
    return NAME_HINTS.get(agent_name.lower(), [])


def classify_task(task_text: str) -> list[tuple[str, int]]:
    """Match task text against capability taxonomy. Returns scored tags as (tag, score) pairs.
    
    Scoring:
    - Each keyword match = 1 point
    - Domain-specific keywords (css, api, sql) worth more than generic ones (fix, bug)
    - Multiple matches in same tag = higher score
    """
    task_lower = task_text.lower()
    scores: dict[str, int] = {}
    
    # Generic keywords that appear in many contexts get lower weight
    generic_keywords = {"fix", "bug", "error", "issue", "problem", "调试", "错误"}
    
    for tag, keywords in CAPABILITY_TAGS.items():
        score = 0
        for kw in keywords:
            if kw in task_lower:
                # Domain-specific keywords worth 2x
                weight = 1 if kw in generic_keywords else 2
                score += weight
        if score > 0:
            scores[tag] = score
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def pick_agent(task_text: str, status: dict, exclude: list[str] | None = None) -> tuple[str, str, list[str]]:
    """Pick the best agent for a task. Returns (agent_name, reason, matched_tags)."""
    exclude = exclude or []
    agents = status.get("agents", {})
    if not agents:
        return "hermes", "no agents on board, defaulting to coordinator", []

    task_tags = classify_task(task_text)
    if not task_tags:
        # No clear match — route to coordinator for triage
        return "hermes", "no capability match, needs triage", []

    # Score each agent
    candidates = []
    for name, data in agents.items():
        if name in exclude:
            continue
        # Skip stale or busy agents unless they're the only option
        agent_status = data.get("status", "unknown")
        last_beat = data.get("last_heartbeat", "")
        is_fresh = False
        if last_beat:
            try:
                beat_time = datetime.fromisoformat(last_beat.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - beat_time).total_seconds()
                is_fresh = age_s < 1800  # 30 min
            except ValueError:
                pass

        caps = get_agent_capabilities(name, data)
        # Match agent capabilities against task tags
        match_score = 0
        matched = []
        for tag, weight in task_tags:
            if tag in caps:
                match_score += weight * (2 if is_fresh else 1)  # Fresh agents get 2x
                matched.append(tag)

        if match_score > 0:
            candidates.append((name, match_score, matched, agent_status, is_fresh))

    if not candidates:
        return "hermes", f"no capable agent for tags {[t for t, _ in task_tags]}", []

    # Sort by score, prefer fresh & idle
    candidates.sort(key=lambda x: (x[1], x[4], x[3] == "idle"), reverse=True)
    winner = candidates[0]
    reason = f"best match for {winner[2]} (score {winner[1]}, {'fresh' if winner[4] else 'stale'}, {winner[3]})"
    return winner[0], reason, winner[2]


def post_handoff(to_agent: str, task: str, reason: str, tags: list[str], bead_id: str | None = None) -> Path:
    """Write a routing handoff to the board."""
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    handoff_id = f"route-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.getpid()}"
    payload = {
        "task": task,
        "reason": reason,
        "matched_tags": tags,
        "router_version": "1.0",
    }
    if bead_id:
        payload["bead"] = bead_id

    handoff = {
        "id": handoff_id,
        "from_agent": ACTOR,
        "to_agent": to_agent,
        "artifact_type": "route",
        "summary": f"Route: {task[:80]}",
        "timestamp": utcnow(),
        "read_by": [],
        "payload": payload,
    }
    path = HANDOFFS / f"{handoff_id}.json"
    path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def create_bead(task: str, assignee: str) -> str | None:
    """Create a beads issue for tracking (if bd CLI available)."""
    try:
        result = subprocess.run(
            ["bd", "create", "--title", task[:100], "-t", "task", "-a", assignee, "--actor", ACTOR],
            cwd=str(BOARD),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # bd create outputs JSON with the new issue ID
            try:
                data = json.loads(result.stdout)
                return data.get("id")
            except json.JSONDecodeError:
                # Fallback: parse from text output
                match = re.search(r"\b(nhood-[a-z0-9]+)\b", result.stdout)
                return match.group(1) if match else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def cmd_route(args: argparse.Namespace) -> int:
    """Route a task to the best agent."""
    status = load_status()
    task = args.task

    # Pick agent
    agent, reason, tags = pick_agent(task, status, exclude=args.exclude or [])

    if args.dry_run:
        print(f"[DRY RUN] Would route to: {agent}")
        print(f"  Reason: {reason}")
        print(f"  Matched tags: {tags}")
        print(f"  Task: {task}")
        return 0

    # Create bead if requested
    bead_id = None
    if args.track:
        bead_id = create_bead(task, agent)
        if bead_id:
            print(f"Created bead: {bead_id}")

    # Post handoff
    path = post_handoff(agent, task, reason, tags, bead_id)
    print(f"Routed to {agent}: {path.name}")
    print(f"  Reason: {reason}")
    if tags:
        print(f"  Tags: {', '.join(tags)}")

    # Rebuild snapshot if requested
    if args.rebuild_snapshot:
        build_py = BOARD / "dashboard" / "build.py"
        if build_py.exists():
            subprocess.run([sys.executable, str(build_py)], cwd=str(BOARD), check=False)
            print("  Snapshot rebuilt")

    return 0


def cmd_update_capabilities(args: argparse.Namespace) -> int:
    """Print a template for declaring capabilities in status.json."""
    print("To declare capabilities, update your agent's entry in:")
    print(f"  {STATUS}")
    print("\nExample:")
    print(json.dumps({
        "agent": "backend-engineer",
        "status": "idle",
        "current_task": None,
        "last_heartbeat": utcnow(),
        "capabilities": ["backend", "api", "database", "debug"]
    }, indent=2))
    print("\nAvailable tags:", ", ".join(sorted(CAPABILITY_TAGS.keys())))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Neighbourhood smart router")
    sub = parser.add_subparsers(dest="cmd", required=True)

    route = sub.add_parser("route", help="Route a task to the best agent")
    route.add_argument("task", help="Task description")
    route.add_argument("--dry-run", action="store_true", help="Show routing decision without posting")
    route.add_argument("--exclude", action="append", help="Exclude an agent from routing")
    route.add_argument("--track", action="store_true", help="Create a beads issue for tracking")
    route.add_argument("--rebuild-snapshot", action="store_true", help="Rebuild dashboard snapshot after routing")
    route.set_defaults(func=cmd_route)

    caps = sub.add_parser("update-capabilities", help="Show how to declare agent capabilities")
    caps.set_defaults(func=cmd_update_capabilities)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
