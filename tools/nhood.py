#!/usr/bin/env python3
"""Gas Town primitives for Neighbourhood — no town, no Mayor, no polecats.

Beads is the data plane. File board stays coordination. Hermes kanban
`neighbourhood` stays dispatcher: this CLI never `hermes kanban --assignee`
(that spawns a live roommate).

Commands: convoy / sling / pour / trail / refine / snapshot-layer / self-check

Refinery (Gas Town primitive, board-only): `nhood.py refine` scans open
convoys and LANDS any whose tracked beads are all closed — closes the
convoy and posts a write-once result handoff. Fails closed: any open
track means no landing, no handoff. No Mayor, no polecats, no kanban.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path


def board_dir() -> Path:
    return Path(
        os.environ.get("NHOOD_HOME")
        or os.environ.get("NEIGHBOURHOOD_BOARD_DIR")
        or (Path.home() / ".neighbourhood")
    )


BOARD = board_dir()
HANDOFFS = BOARD / "handoffs"
FORMULAS = BOARD / ".beads" / "formulas"
ACTOR = os.environ.get("NHOOD_AGENT") or os.environ.get("BEADS_ACTOR") or "hermes"
STALE_S = 45 * 60


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def which_bd() -> str:
    exe = shutil.which("bd") or shutil.which("bd.cmd") or shutil.which("bd.exe")
    if not exe:
        raise SystemExit("bd CLI not on PATH (Windows: bd.cmd npm shim)")
    return exe


def bd(args: list[str], timeout_s: int = 20) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("BEADS_ACTOR", ACTOR)
    return subprocess.run(
        [which_bd(), *args],
        cwd=str(BOARD),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env=env,
    )


def bd_json(args: list[str], timeout_s: int = 20):
    extra = [] if "--json" in args else ["--json"]
    try:
        proc = bd([*args, *extra], timeout_s=timeout_s)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"bd failed: {exc}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise SystemExit(f"bd {' '.join(args)}: {err[:500]}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"bd json decode failed: {exc}") from exc


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def dump(data) -> None:
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def slim_issue(issue: dict) -> dict:
    return {
        "id": issue.get("id"),
        "title": issue.get("title"),
        "status": issue.get("status"),
        "priority": issue.get("priority"),
        "issue_type": issue.get("issue_type") or issue.get("type"),
        "assignee": issue.get("assignee"),
        "parent": issue.get("parent"),
        "labels": issue.get("labels") or [],
        "updated_at": issue.get("updated_at"),
    }


def list_issues(args: list[str]) -> list[dict]:
    data = bd_json(args)
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        return [i for i in data["issues"] if isinstance(i, dict)]
    return []


def show_issue(issue_id: str) -> dict:
    data = bd_json(["show", issue_id])
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else {"id": issue_id}
    if isinstance(data, dict):
        return data
    return {"id": issue_id}


def track_ids_from_deps(records) -> list[str]:
    ids: list[str] = []
    if not isinstance(records, list):
        return ids
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for key in (
            "depends_on_id",
            "to_id",
            "to_key",
            "target_id",
            "depends_on",
            "to",
            "target",
        ):
            val = rec.get(key)
            if isinstance(val, str) and val.startswith("nhood-"):
                ids.append(val)
                break
        else:
            src = rec.get("issue_id") or rec.get("from_id") or rec.get("from")
            other = rec.get("depends_on_id") or rec.get("to_id")
            for cand in (other, rec.get("id")):
                if isinstance(cand, str) and cand.startswith("nhood-") and cand != src:
                    ids.append(cand)
                    break
    # unique preserve order
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def convoy_tracks(convoy_id: str) -> list[dict]:
    try:
        recs = bd_json(
            ["dep", "list", convoy_id, "--direction", "down", "--type", "tracks"]
        )
    except SystemExit:
        recs = []
    ids = track_ids_from_deps(recs)
    if not ids and isinstance(recs, list):
        for rec in recs:
            if isinstance(rec, dict):
                for val in rec.values():
                    if isinstance(val, str) and val.startswith("nhood-") and val != convoy_id:
                        ids.append(val)
    tracks = []
    for tid in ids:
        try:
            tracks.append(slim_issue(show_issue(tid)))
        except SystemExit:
            tracks.append({"id": tid, "title": None, "status": "unknown"})
    return tracks


def enrich_convoy(issue: dict) -> dict:
    row = slim_issue(issue)
    tracks = convoy_tracks(row["id"])
    closed = sum(1 for t in tracks if (t.get("status") or "") == "closed")
    total = len(tracks)
    row["tracks"] = tracks
    row["closed"] = closed
    row["total"] = total
    row["landed"] = bool(total) and closed == total
    return row


def cmd_convoy_create(args: argparse.Namespace) -> int:
    created = bd_json(
        [
            "create",
            "--title",
            args.title,
            "-t",
            "convoy",
            "-l",
            "convoy",
            "-p",
            str(args.priority),
            "--actor",
            ACTOR,
            "--description",
            args.description
            or "Neighbourhood convoy (Gas Town steal). Tracks are non-blocking.",
        ]
    )
    convoy_id = created.get("id") if isinstance(created, dict) else None
    if not convoy_id:
        raise SystemExit(f"convoy create returned no id: {created}")
    tracks = [t.strip() for t in (args.tracks or "").split(",") if t.strip()]
    for tid in tracks:
        bd_json(
            ["dep", "add", convoy_id, tid, "-t", "tracks", "--actor", ACTOR]
        )
    dump({"id": convoy_id, "title": args.title, "tracks": tracks})
    return 0


def cmd_convoy_list(_args: argparse.Namespace) -> int:
    rows = list_issues(["list", "--type", "convoy", "--all", "--flat", "--limit", "50"])
    if not rows:
        rows = list_issues(["list", "--label", "convoy", "--all", "--flat", "--limit", "50"])
    dump([enrich_convoy(r) for r in rows])
    return 0


def cmd_convoy_status(args: argparse.Namespace) -> int:
    dump(enrich_convoy(show_issue(args.id)))
    return 0


def cmd_convoy_check(_args: argparse.Namespace) -> int:
    rows = list_issues(["list", "--type", "convoy", "--flat", "--limit", "50"])
    if not rows:
        rows = list_issues(["list", "--label", "convoy", "--flat", "--limit", "50"])
    closed = []
    for row in rows:
        if (row.get("status") or "") == "closed":
            continue
        info = enrich_convoy(row)
        if info.get("landed"):
            bd_json(
                [
                    "close",
                    info["id"],
                    "--reason",
                    "all tracked issues closed",
                    "--actor",
                    ACTOR,
                ]
            )
            closed.append(info["id"])
    dump({"closed": closed})
    return 0


def refine_convoy(convoy_id: str, dry_run: bool = False) -> dict:
    """Land one convoy iff every tracked bead is closed.

    Fail-closed: any track not closed -> skip, no close, no handoff.
    Landing: bd close + write-once result handoff to ALL (no kanban).
    """
    info = enrich_convoy(show_issue(convoy_id))
    if (info.get("status") or "") == "closed":
        return {"id": convoy_id, "landed": False, "skipped": "already-closed"}
    open_tracks = [t for t in info.get("tracks", []) if (t.get("status") or "") != "closed"]
    if open_tracks:
        return {
            "id": convoy_id,
            "landed": False,
            "blocked_on": [t.get("id") for t in open_tracks],
        }
    result = {
        "id": convoy_id,
        "title": info.get("title"),
        "landed": not dry_run,
        "dry_run": dry_run,
        "tracks_closed": [t.get("id") for t in info.get("tracks", [])],
        "total": info.get("total", len(info.get("tracks", []))),
    }
    if dry_run:
        return result
    bd_json(
        [
            "close",
            convoy_id,
            "--reason",
            f"refinery: all {result['total']} tracked beads closed",
            "--actor",
            ACTOR,
        ]
    )
    path = write_handoff(
        from_agent=ACTOR,
        to_agent="ALL",
        artifact_type="result",
        summary=f"refinery LANDED {convoy_id}: {info.get('title') or convoy_id} "
        f"({result['total']}/{result['total']} tracks closed)",
        payload={
            "convoy": convoy_id,
            "tracks_closed": result["tracks_closed"],
            "lander": ACTOR,
            "primitive": "refinery",
        },
    )
    result["handoff"] = path.name
    return result


def cmd_refine(args: argparse.Namespace) -> int:
    if args.id:
        results = [refine_convoy(args.id, dry_run=args.dry_run)]
    else:
        rows = list_issues(["list", "--type", "convoy", "--flat", "--limit", "50"])
        if not rows:
            rows = list_issues(["list", "--label", "convoy", "--flat", "--limit", "50"])
        results = [
            refine_convoy(r["id"], dry_run=args.dry_run)
            for r in rows
            if (r.get("status") or "") != "closed"
        ]
    landed = [r for r in results if r.get("landed")]
    dump({"landed": len(landed), "results": results})
    return 0


def write_handoff(
    *,
    from_agent: str,
    to_agent: str,
    artifact_type: str,
    summary: str,
    payload: dict,
    files_changed: list[str] | None = None,
) -> Path:
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    hid = str(uuid.uuid4())
    body = {
        "id": hid,
        "timestamp": utcnow(),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "artifact_type": artifact_type,
        "summary": summary,
        "payload": payload,
        "files_changed": files_changed or [],
        "read_by": [],
    }
    path = HANDOFFS / f"{hid}.json"
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def cmd_sling(args: argparse.Namespace) -> int:
    issue = show_issue(args.id)
    if not issue.get("id"):
        raise SystemExit(f"unknown bead {args.id}")
    update = [
        "update",
        args.id,
        "-a",
        args.to,
        "--add-label",
        "slung",
        "--actor",
        ACTOR,
    ]
    if args.claim:
        update.append("--claim")
    bd_json(update)
    convoy_id = None
    if not args.no_convoy:
        title = f"Work: {issue.get('title') or args.id}"
        created = bd_json(
            [
                "create",
                "--title",
                title,
                "-t",
                "convoy",
                "-l",
                "convoy",
                "-p",
                "2",
                "--actor",
                ACTOR,
                "--description",
                f"Auto-convoy for sling of {args.id} to {args.to}",
            ]
        )
        convoy_id = created.get("id") if isinstance(created, dict) else None
        if convoy_id:
            bd_json(
                ["dep", "add", convoy_id, args.id, "-t", "tracks", "--actor", ACTOR]
            )
    summary = args.summary or f"Sling {args.id} → {args.to} (no kanban dispatch)"
    path = write_handoff(
        from_agent=args.from_agent,
        to_agent=args.to,
        artifact_type="sling",
        summary=summary,
        payload={
            "bead": args.id,
            "title": issue.get("title"),
            "convoy": convoy_id,
            "claim": bool(args.claim),
            "no_kanban_assign": True,
        },
    )
    dump(
        {
            "bead": args.id,
            "to": args.to,
            "convoy": convoy_id,
            "handoff": path.name,
            "claim": bool(args.claim),
        }
    )
    return 0


def subst(text: str, variables: dict[str, str]) -> str:
    out = text or ""
    for key, val in variables.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def load_formula(name: str) -> dict:
    path = FORMULAS / f"{name}.formula.toml"
    if not path.is_file():
        # gt formula create uses this name; also allow name.formula.toml vs name.toml
        alt = FORMULAS / f"{name}.toml"
        path = alt if alt.is_file() else path
    if not path.is_file():
        raise SystemExit(f"formula not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    data["_path"] = str(path)
    return data


def cmd_pour(args: argparse.Namespace) -> int:
    formula = load_formula(args.formula)
    variables: dict[str, str] = {}
    for item in args.var or []:
        if "=" not in item:
            raise SystemExit(f"--var needs key=value, got {item}")
        key, val = item.split("=", 1)
        variables[key.strip()] = val
    missing = []
    for name, spec in (formula.get("vars") or {}).items():
        if isinstance(spec, dict) and spec.get("required") and name not in variables:
            missing.append(name)
    if missing:
        raise SystemExit(f"formula requires --var {', '.join(missing)}=...")
    feature = variables.get("feature") or args.formula
    steps = formula.get("steps") or []
    root_title = subst(f"Mol: {feature}", variables)
    nodes = [{"key": "root", "title": root_title, "type": "epic"}]
    edges = []
    for step in steps:
        sid = step.get("id")
        if not sid:
            continue
        nodes.append(
            {
                "key": sid,
                "title": subst(step.get("title") or sid, variables),
                "type": "task",
                "parent_key": "root",
            }
        )
        for need in step.get("needs") or []:
            edges.append({"from_key": sid, "to_key": need, "type": "blocks"})
    plan = {"nodes": nodes, "edges": edges}
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="nhood-pour-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(plan, tmp)
        plan_path = tmp.name
    try:
        created = bd_json(["create", "--graph", plan_path, "--actor", ACTOR])
    finally:
        Path(plan_path).unlink(missing_ok=True)
    root_id = None
    created_ids = []
    raw_nodes = []
    if isinstance(created, dict):
        raw_nodes = created.get("nodes") or created.get("created") or created.get("ids") or []
        root_id = created.get("id")
    elif isinstance(created, list):
        raw_nodes = created
    for node in raw_nodes:
        if isinstance(node, str) and node:
            created_ids.append(node)
            continue
        if isinstance(node, dict) and node.get("id"):
            created_ids.append(node["id"])
            if node.get("key") == "root" or (node.get("title") or "").startswith("Mol:"):
                root_id = node["id"]
    if not root_id:
        for cid in created_ids:
            try:
                shown = show_issue(cid)
            except SystemExit:
                continue
            title = shown.get("title") or ""
            itype = shown.get("issue_type") or shown.get("type")
            if title.startswith("Mol:") or itype == "epic":
                root_id = cid
                break
    if args.parent and root_id:
        bd_json(["update", root_id, "--parent", args.parent, "--actor", ACTOR])
    dump(
        {
            "formula": args.formula,
            "root": root_id,
            "created": created_ids,
            "raw_keys": list(created) if isinstance(created, dict) else type(created).__name__,
        }
    )
    return 0


def git_trail(limit: int) -> list[dict]:
    git = shutil.which("git") or shutil.which("git.exe")
    if not git:
        return []
    try:
        proc = subprocess.run(
            [
                git,
                "-C",
                str(BOARD),
                "log",
                f"-n{limit}",
                "--format=%h%x09%cI%x09%s",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        rows.append(
            {
                "kind": "git",
                "id": parts[0],
                "at": parts[1],
                "title": parts[2],
            }
        )
    return rows


def handoff_trail(limit: int) -> list[dict]:
    if not HANDOFFS.is_dir():
        return []
    rows = []
    paths = sorted(HANDOFFS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths[:limit]:
        data = read_json(path, None)
        if not isinstance(data, dict):
            continue
        rows.append(
            {
                "kind": "handoff",
                "id": data.get("id") or path.stem,
                "at": data.get("timestamp"),
                "title": f"{data.get('from_agent')} → {data.get('to_agent')}: {data.get('summary')}",
                "artifact_type": data.get("artifact_type"),
            }
        )
    return rows


def bead_trail(limit: int) -> list[dict]:
    try:
        issues = list_issues(
            ["list", "--all", "--flat", "--sort", "updated", "--limit", str(limit)]
        )
    except SystemExit:
        return []
    rows = []
    for issue in issues:
        rows.append(
            {
                "kind": "bead",
                "id": issue.get("id"),
                "at": issue.get("updated_at") or issue.get("created_at"),
                "title": f"{issue.get('id')} [{issue.get('status')}] {issue.get('title')}",
            }
        )
    return rows


def merge_trail(limit: int) -> list[dict]:
    rows = git_trail(limit) + handoff_trail(limit) + bead_trail(limit)
    def key(row: dict):
        dt = parse_iso(row.get("at"))
        return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

    rows.sort(key=key, reverse=True)
    return rows[:limit]


def list_formulas() -> list[dict]:
    if not FORMULAS.is_dir():
        return []
    rows = []
    for path in sorted(FORMULAS.glob("*.toml")):
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        steps = data.get("steps") or []
        rows.append(
            {
                "name": data.get("formula") or path.stem.replace(".formula", ""),
                "description": (data.get("description") or "").strip().splitlines()[0]
                if data.get("description")
                else "",
                "steps": [s.get("id") for s in steps if isinstance(s, dict) and s.get("id")],
                "path": str(path),
            }
        )
    return rows


def stale_from_status() -> list[dict]:
    status = read_json(BOARD / "status.json", {})
    agents = list((status.get("agents") or {}).values())
    now = datetime.now(timezone.utc)
    stale = []
    for agent in agents:
        hb = parse_iso(agent.get("last_heartbeat"))
        if not hb:
            stale.append({**{k: agent.get(k) for k in ("agent", "status", "last_heartbeat")}, "reason": "no heartbeat"})
            continue
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        age = (now - hb).total_seconds()
        if age > STALE_S:
            stale.append(
                {
                    "agent": agent.get("agent"),
                    "status": agent.get("status"),
                    "last_heartbeat": agent.get("last_heartbeat"),
                    "age_s": int(age),
                    "reason": "heartbeat older than 45m",
                }
            )
    return stale


def cmd_trail(args: argparse.Namespace) -> int:
    dump(merge_trail(args.limit))
    return 0


def cmd_snapshot_layer(_args: argparse.Namespace) -> int:
    convoys = []
    try:
        rows = list_issues(["list", "--type", "convoy", "--all", "--flat", "--limit", "40"])
        if not rows:
            rows = list_issues(
                ["list", "--label", "convoy", "--all", "--flat", "--limit", "40"]
            )
        convoys = [enrich_convoy(r) for r in rows]
    except SystemExit:
        convoys = []
    dump(
        {
            "convoys": convoys,
            "trail": merge_trail(16),
            "formulas": list_formulas(),
            "stale_agents": stale_from_status(),
            "gated": ["gt install ~/gt", "Mayor", "polecats", "beads-mcp"],
        }
    )
    return 0


def cmd_self_check(_args: argparse.Namespace) -> int:
    problems = []
    if not BOARD.is_dir():
        problems.append("missing ~/.neighbourhood")
    status_path = BOARD / "status.json"
    if not status_path.is_file():
        problems.append("missing status.json")
    else:
        status = read_json(status_path, None)
        if not isinstance(status, dict):
            problems.append("status.json unparseable")
    if not HANDOFFS.is_dir():
        problems.append("missing handoffs/")
    try:
        which_bd()
    except SystemExit as exc:
        problems.append(str(exc))
    formula = FORMULAS / "nhood-feature.formula.toml"
    if not formula.is_file():
        problems.append("missing nhood-feature formula")
    else:
        try:
            load_formula("nhood-feature")
        except SystemExit as exc:
            problems.append(str(exc))
    try:
        types = bd(["types"], timeout_s=8)
        if "convoy" not in (types.stdout or ""):
            problems.append("types.custom convoy not visible in bd types")
    except (OSError, subprocess.TimeoutExpired, SystemExit):
        problems.append("bd types failed")
    dump({"ok": not problems, "problems": problems, "board": str(BOARD)})
    return 0 if not problems else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nhood")
    sub = p.add_subparsers(dest="cmd", required=True)

    conv = sub.add_parser("convoy", help="Track a batch of beads (non-blocking)")
    csub = conv.add_subparsers(dest="ccmd", required=True)
    cc = csub.add_parser("create")
    cc.add_argument("title")
    cc.add_argument("--tracks", default="", help="comma-separated bead ids")
    cc.add_argument("-p", "--priority", default="2")
    cc.add_argument("-d", "--description", default="")
    cc.set_defaults(func=cmd_convoy_create)
    cl = csub.add_parser("list")
    cl.set_defaults(func=cmd_convoy_list)
    cs = csub.add_parser("status")
    cs.add_argument("id")
    cs.set_defaults(func=cmd_convoy_status)
    ck = csub.add_parser("check")
    ck.set_defaults(func=cmd_convoy_check)

    sl = sub.add_parser("sling", help="Assign a bead + write-once handoff (no kanban spawn)")
    sl.add_argument("id")
    sl.add_argument("--to", required=True, help="agent name (file board), not a kanban assignee")
    sl.add_argument("--summary", default="")
    sl.add_argument("--from-agent", default=ACTOR)
    sl.add_argument("--claim", action="store_true", help="also bd update --claim")
    sl.add_argument("--no-convoy", action="store_true")
    sl.set_defaults(func=cmd_sling)

    po = sub.add_parser("pour", help="Instantiate a formula into beads (not gt formula run)")
    po.add_argument("formula")
    po.add_argument("--var", action="append", default=[], help="key=value")
    po.add_argument("--parent", default="", help="parent bead for the molecule epic")
    po.set_defaults(func=cmd_pour)

    tr = sub.add_parser("trail", help="Activity feed: git + handoffs + beads")
    tr.add_argument("--limit", type=int, default=16)
    tr.set_defaults(func=cmd_trail)

    rf = sub.add_parser(
        "refine",
        help="Refinery: land convoys whose tracks are all closed (fail-closed, result handoff)",
    )
    rf.add_argument("--id", default="", help="refine only this convoy")
    rf.add_argument(
        "--dry-run", action="store_true", help="report what would land; no close, no handoff"
    )
    rf.set_defaults(func=cmd_refine)

    snap = sub.add_parser("snapshot-layer", help="JSON blob for dashboard/build.py")
    snap.set_defaults(func=cmd_snapshot_layer)

    sc = sub.add_parser("self-check")
    sc.set_defaults(func=cmd_self_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print("bd/git timed out", file=sys.stderr)
        raise SystemExit(1)
