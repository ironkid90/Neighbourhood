#!/usr/bin/env python3
"""Build a read-only Neighbourhood dashboard from local JSON files.

No network, no secrets, no writes outside this dashboard/ folder except
an optional heartbeat into ~/.neighbourhood/status.json (own agent only).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
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
DASH = BOARD / "dashboard"
HUB = Path(os.environ.get("MCP_HUB") or (Path.home() / ".mcp-hub"))
HEALTH_JSON = HUB / "backups" / "health.json"
HEALTH_LOG = HUB / "backups" / "health-latest.log"
MCP_JSON = HUB / "mcp.json"
PREFLIGHT_JSON = BOARD / "preflight" / "health.json"


def courier_dir() -> Path:
    candidates = [
        BOARD / "courier",
        Path(__file__).resolve().parents[1] / "courier",
        Path.home() / "Documents" / "github" / "Neighbourhood" / "courier",
        Path.home() / "Documents" / "github" / "context-orchestrator" / "courier",
    ]
    for cand in candidates:
        if (cand / "neighbourhood_courier.py").is_file():
            return cand
    return candidates[0]


COURIER = courier_dir()


def hermes_home() -> Path:
    """App root, not a profile dir. HERMES_HOME may be <root>/profiles/<name>."""
    candidates: list[Path] = []
    env = os.environ.get("HERMES_HOME")
    if env:
        candidates.append(Path(env))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "hermes")
    candidates.append(Path.home() / ".hermes")
    for cand in candidates:
        p = cand
        for _ in range(8):
            if (p / "desktop-plugins").is_dir():
                return p
            parent = p.parent
            if parent == p:
                break
            p = parent
    return candidates[0]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def read_json(path: Path, default):
    # utf-8-sig: PS 5.1 Set-Content -Encoding UTF8 writes a BOM that breaks utf-8.
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def load_handoffs() -> list[dict]:
    folder = BOARD / "handoffs"
    if not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = read_json(path, None)
        if isinstance(data, dict):
            data["_file"] = path.name
            rows.append(data)
    return rows


def parse_health_log_last(text: str) -> dict | None:
    blocks = re.split(r"(?m)^===== ", text)
    if len(blocks) < 2:
        return None
    last = "===== " + blocks[-1].strip()
    header = re.search(r"===== (.+?) =====", last)
    servers = []
    for m in re.finditer(
        r"^\s+(PASS|FAIL)\s+(\S+)\s+\[(\w+)\]:\s*(.*)$", last, re.M
    ):
        servers.append(
            {
                "name": m.group(2),
                "pass": m.group(1) == "PASS",
                "status": m.group(3),
                "detail": m.group(4).strip(),
            }
        )
    exit_m = re.search(r"exit=(\d+)", last)
    return {
        "source": "health-latest.log",
        "checked_at": header.group(1).strip() if header else None,
        "exit": int(exit_m.group(1)) if exit_m else None,
        "all_verified_pass": "All verified servers pass" in last,
        "servers": servers,
        "raw_header": last.splitlines()[0] if last else "",
    }


def load_health() -> dict:
    file_data = read_json(HEALTH_JSON, {})
    file_servers = []
    for name, info in (file_data.get("servers") or {}).items():
        file_servers.append(
            {
                "name": name,
                "pass": bool(info.get("pass")),
                "status": info.get("status"),
                "detail": str(info.get("detail") or "")[:240],
            }
        )
    from_file = {
        "source": "health.json",
        "checked_at": file_data.get("checked_at"),
        "servers": file_servers,
    }
    log = None
    if HEALTH_LOG.is_file():
        log = parse_health_log_last(HEALTH_LOG.read_text(encoding="utf-8-sig", errors="replace"))
    # Prefer the log stanza when it exists — health.json has been observed stale
    # after a PATH-poisoned probe while the log already recorded a later PASS.
    primary = log if log and log.get("servers") else from_file
    return {"primary": primary, "file": from_file, "log": log, "stale_file": bool(
        log and from_file.get("checked_at") and log.get("checked_at")
        and str(from_file.get("checked_at"))[:16] != str(log.get("checked_at"))[:16]
        and any(not s.get("pass") for s in file_servers)
        and log.get("all_verified_pass")
    )}


def load_preflight() -> dict:
    data = read_json(PREFLIGHT_JSON, None)
    if not isinstance(data, dict) or not data.get("checks"):
        return {"available": False}
    checks = []
    for c in data.get("checks") or []:
        checks.append(
            {
                "name": c.get("name"),
                "status": c.get("status"),
                "detail": str(c.get("detail") or "")[:240],
            }
        )
    return {
        "available": True,
        "source": "preflight/health.json",
        "checked_at": data.get("ts"),
        "overall": data.get("overall") or "unknown",
        "checks": checks,
    }


def load_mcp_meta() -> list[dict]:
    data = read_json(MCP_JSON, {})
    servers = data.get("mcpServers") or data.get("servers") or {}
    rows = []
    for name, cfg in servers.items():
        meta = cfg.get("_meta") or {}
        rows.append(
            {
                "name": name,
                "status": meta.get("_status") or "unknown",
                "category": meta.get("_category"),
                "command": cfg.get("command"),
            }
        )
    return rows


def bd_query(args: list[str], timeout_s: int = 8) -> list[dict] | None:
    """Run `bd <args> --json` in the board repo. None on any failure (CLI missing,
    timeout, bad JSON) — the dashboard must build even when beads is absent.
    On Windows `bd` is an npm shim (bd.cmd), so resolve via shutil.which — bare
    'bd' is not a CreateProcess-able executable."""
    exe = shutil.which("bd") or shutil.which("bd.cmd") or shutil.which("bd.exe")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, *args, "--json"],
            cwd=str(BOARD),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def slim_issue(i: dict) -> dict:
    return {
        "id": i.get("id"),
        "title": i.get("title"),
        "status": i.get("status"),
        "priority": i.get("priority"),
        "issue_type": i.get("issue_type"),
        "assignee": i.get("assignee"),
        "parent": i.get("parent"),
    }


def load_beads() -> dict:
    ready = bd_query(["ready"])
    in_progress = bd_query(["list", "--status", "in_progress"])
    blocked = bd_query(["list", "--status", "blocked"])
    if ready is None and in_progress is None and blocked is None:
        return {"available": False, "source": "bd CLI (cwd ~/.neighbourhood)"}
    return {
        "available": True,
        "source": "bd ready --json",
        "ready": [slim_issue(i) for i in (ready or [])],
        "in_progress": [slim_issue(i) for i in (in_progress or [])],
        "blocked": [slim_issue(i) for i in (blocked or [])],
    }


def load_gastown_lite() -> dict:
    """Pull convoy/trail/formula from tools/nhood.py. Fail closed."""
    empty = {
        "available": False,
        "convoys": [],
        "trail": [],
        "formulas": [],
        "stale_agents": [],
        "gated": ["gt install ~/gt", "Mayor", "polecats", "beads-mcp"],
    }
    script = BOARD / "tools" / "nhood.py"
    if not script.is_file():
        return empty
    try:
        out = subprocess.run(
            [sys.executable, str(script), "snapshot-layer"],
            cwd=str(BOARD),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        empty["error"] = "snapshot-layer timeout"
        return empty
    except OSError as exc:
        empty["error"] = f"snapshot-layer oserror: {exc}"
        return empty
    if out.returncode != 0:
        empty["error"] = f"snapshot-layer exit {out.returncode}"
        return empty
    try:
        data = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        empty["error"] = "snapshot-layer json"
        return empty
    if not isinstance(data, dict):
        return empty
    empty.update(data)
    empty["available"] = True
    return empty


def courier_state() -> dict:
    script = COURIER / "neighbourhood_courier.py"
    cfg = COURIER / "courier-config.json"
    return {
        "script_present": script.is_file(),
        "config_present": cfg.is_file(),
        "mode": "configured" if cfg.is_file() else "dry-run (no courier-config.json)",
        "path": str(script) if script.is_file() else None,
    }


def snapshot() -> dict:
    status = read_json(BOARD / "status.json", {})
    handoffs = load_handoffs()
    unread = sum(1 for h in handoffs if not h.get("read_by"))
    health = load_health()
    primary = health["primary"]
    verified_fail = [
        s["name"]
        for s in primary.get("servers") or []
        if s.get("status") == "verified" and not s.get("pass")
    ]
    lite = load_gastown_lite()
    return {
        "built_at": utcnow(),
        "board": str(BOARD),
        "status": status,
        "agents": list((status.get("agents") or {}).values()),
        "handoffs": handoffs,
        "unread_handoffs": unread,
        "health": health,
        "preflight": load_preflight(),
        "mcp": load_mcp_meta(),
        "beads": load_beads(),
        "convoys": lite.get("convoys") or [],
        "trail": lite.get("trail") or [],
        "formulas": lite.get("formulas") or [],
        "stale_agents": lite.get("stale_agents") or [],
        "gastown_lite": bool(lite.get("available")),
        "gated": lite.get("gated")
        or ["gt install ~/gt", "Mayor", "polecats", "beads-mcp"],
        "courier": courier_state(),
        "mcp_verified_fail": verified_fail,
        "workstreams": [
            {
                "id": "env",
                "title": "Env / path hardening",
                "owner": "backend-engineer",
                "status": "claimed",
                "note": "preflight.ps1 — path sanity, MCP drift vs ~/.mcp-hub/mcp.json, port 5051, npx nopt-lib PATH poison",
            },
            {
                "id": "dash",
                "title": "Read-only GUI dashboard",
                "owner": "hermes",
                "status": "done",
                "note": "HTML + Hermes desktop pane (sidebar Neighbourhood). Snapshot copied next to plugin.js; live REST needs plugins.enabled + gateway restart (not done).",
            },
            {
                "id": "gtlite",
                "title": "Gastown-lite (convoy/sling/formula/trail)",
                "owner": "hermes",
                "status": "done",
                "note": "tools/nhood.py + dashboard dock. Beads type convoy + tracks. No gt install/Mayor/polecats/beads-mcp.",
            },
            {
                "id": "mem",
                "title": "Memory hygiene",
                "owner": "hermes",
                "status": "ready",
                "note": "Mem0 custom_instructions applied; skip proc IDs. Prefer hub backup prompt over generic copilot draft.",
            },
            {
                "id": "courier",
                "title": "Telegram courier",
                "owner": "unclaimed",
                "status": "ready",
                "note": "Ships in-repo at courier/neighbourhood_courier.py. Dry-run until courier-config.json. Prefer Hermes cron --no-agent over a second long-running bot.",
            },
            {
                "id": "pkg",
                "title": "One-click packaged app",
                "owner": "hermes",
                "status": "done",
                "note": "Product repo Documents/github/Neighbourhood — Install.cmd syncs board + desktop plugin + snapshot.",
            },
            {
                "id": "hub",
                "title": "MCP hub flexibility",
                "owner": "unclaimed",
                "status": "gated",
                "note": "Plan-first. Do not edit mcp.json / live config.yaml until human says go.",
            },
        ],
    }


def esc(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render(data: dict) -> str:
    agents = data["agents"]
    handoffs = data["handoffs"]
    health = data["health"]["primary"]
    mcp = data["mcp"]
    work = data["workstreams"]
    courier = data["courier"]
    stale = data["health"].get("stale_file")

    def agent_cards() -> str:
        if not agents:
            return '<div class="empty">No heartbeats yet</div>'
        bits = []
        for a in agents:
            st = esc(a.get("status") or "unknown")
            bits.append(
                f"""<article class="card" data-status="{st}">
  <div class="row"><span class="dot"></span><strong>{esc(a.get("agent"))}</strong><span class="pill">{st}</span></div>
  <div class="muted">{esc(a.get("current_task") or "idle")}</div>
  <div class="tiny">{esc(a.get("note") or "")}</div>
  <div class="tiny">hb {esc(a.get("last_heartbeat") or "—")}</div>
</article>"""
            )
        return "\n".join(bits)

    def handoff_cards() -> str:
        if not handoffs:
            return '<div class="empty">No handoffs</div>'
        bits = []
        for h in handoffs[:12]:
            unread = "unread" if not h.get("read_by") else "read"
            bits.append(
                f"""<article class="card {unread}">
  <div class="row"><strong>{esc(h.get("from_agent"))} → {esc(h.get("to_agent"))}</strong><span class="pill">{esc(h.get("artifact_type"))}</span></div>
  <div>{esc(h.get("summary"))}</div>
  <div class="tiny">{esc(h.get("timestamp"))} · {esc(h.get("id","")[:8])}</div>
</article>"""
            )
        return "\n".join(bits)

    def server_rows(servers, title) -> str:
        if not servers:
            return f'<div class="empty">{esc(title)}: none</div>'
        rows = [
            "<table><thead><tr><th></th><th>server</th><th>status</th><th>detail</th></tr></thead><tbody>"
        ]
        for s in servers:
            ok = "ok" if s.get("pass") else "bad"
            mark = "PASS" if s.get("pass") else "FAIL"
            rows.append(
                f"<tr data-ok='{ok}'><td class='mark'>{mark}</td><td>{esc(s.get('name'))}</td>"
                f"<td>{esc(s.get('status'))}</td><td class='tiny'>{esc(s.get('detail'))}</td></tr>"
            )
        rows.append("</tbody></table>")
        return "\n".join(rows)

    def mcp_rows() -> str:
        rows = [
            "<table><thead><tr><th>server</th><th>_status</th><th>category</th></tr></thead><tbody>"
        ]
        for s in mcp:
            rows.append(
                f"<tr><td>{esc(s['name'])}</td><td>{esc(s['status'])}</td><td>{esc(s.get('category') or '')}</td></tr>"
            )
        rows.append("</tbody></table>")
        return "\n".join(rows)

    def preflight_rows() -> str:
        pre = data["preflight"]
        if not pre.get("available"):
            return '<div class="empty">preflight not run yet — powershell -NoProfile -ExecutionPolicy Bypass -File ~/.neighbourhood/preflight/preflight.ps1</div>'
        rows = [
            "<table><thead><tr><th></th><th>check</th><th>detail</th></tr></thead><tbody>"
        ]
        for c in pre.get("checks") or []:
            tone = {"PASS": "ok", "WARN": "warn", "FAIL": "bad"}.get(c.get("status"), "ok")
            rows.append(
                f"<tr data-ok='{tone}'><td class='mark'>{esc(c.get('status'))}</td>"
                f"<td>{esc(c.get('name'))}</td><td class='tiny'>{esc(c.get('detail'))}</td></tr>"
            )
        rows.append("</tbody></table>")
        return "\n".join(rows)

    def beads_rows() -> str:
        beads = data["beads"]
        if not beads.get("available"):
            return '<div class="empty">bd CLI unavailable in this shell — snapshot built without beads.</div>'
        bits = []

        def group(label: str, items: list[dict]) -> None:
            bits.append(f'<div class="tiny" style="margin-top:6px">{esc(label)} ({len(items)})</div>')
            if not items:
                bits.append('<div class="empty" style="padding:4px 0">none</div>')
                return
            for i in items:
                meta = []
                if i.get("priority") is not None:
                    meta.append(f"P{i['priority']}")
                if i.get("issue_type"):
                    meta.append(str(i["issue_type"]))
                if i.get("assignee"):
                    meta.append(f"@{i['assignee']}")
                bits.append(
                    f"""<article class="card" data-status="{esc(i.get('status') or '')}">
  <div class="row"><strong>{esc(i.get("id"))}</strong><span class="pill">{esc(" · ".join(meta))}</span></div>
  <div class="muted">{esc(i.get("title") or "")}</div>
</article>"""
                )

        group("in progress", beads.get("in_progress") or [])
        group("ready", beads.get("ready") or [])
        group("blocked", beads.get("blocked") or [])
        return "\n".join(bits)

    def convoy_cards() -> str:
        convoys = data.get("convoys") or []
        if not convoys:
            return '<div class="empty">No convoys — python tools/nhood.py convoy create "Title" --tracks id</div>'
        bits = []
        for c in convoys[:8]:
            landed = "landed" if c.get("landed") else (c.get("status") or "open")
            tracks = c.get("tracks") or []
            track_txt = ", ".join(
                f"{t.get('id')} {t.get('status')}" for t in tracks[:6]
            ) or "no tracks"
            bits.append(
                f"""<article class="card" data-status="{esc(landed)}">
  <div class="row"><strong>{esc(c.get("id"))}</strong><span class="pill">{esc(c.get("closed"))}/{esc(c.get("total"))} {esc(landed)}</span></div>
  <div>{esc(c.get("title") or "")}</div>
  <div class="tiny">{esc(track_txt)}</div>
</article>"""
            )
        return "\n".join(bits)

    def trail_rows() -> str:
        trail = data.get("trail") or []
        if not trail:
            return '<div class="empty">No trail yet</div>'
        bits = []
        for t in trail[:16]:
            bits.append(
                f"""<article class="card">
  <div class="row"><strong>{esc(t.get("kind"))}</strong><span class="tiny">{esc(t.get("at") or "")}</span></div>
  <div class="muted">{esc(t.get("title") or t.get("id") or "")}</div>
</article>"""
            )
        return "\n".join(bits)

    def formula_rows() -> str:
        formulas = data.get("formulas") or []
        if not formulas:
            return '<div class="empty">No formulas in .beads/formulas</div>'
        bits = []
        for fml in formulas:
            steps = " → ".join(fml.get("steps") or [])
            bits.append(
                f"""<article class="card">
  <div class="row"><strong>{esc(fml.get("name"))}</strong></div>
  <div class="tiny">{esc(steps)}</div>
  <div class="muted">{esc(fml.get("description") or "")}</div>
</article>"""
            )
        return "\n".join(bits)

    def work_cols() -> str:
        bits = []
        for w in work:
            bits.append(
                f"""<article class="card" data-col="{esc(w['status'])}">
  <div class="tiny">{esc(w['status'])} · {esc(w['owner'])}</div>
  <strong>{esc(w['title'])}</strong>
  <div class="muted">{esc(w['note'])}</div>
</article>"""
            )
        return "\n".join(bits)

    fail = data["mcp_verified_fail"]
    health_tone = "bad" if fail else "ok"
    pre = data["preflight"]
    pre_tone = (
        "bad" if pre.get("overall") == "FAIL"
        else "warn" if pre.get("overall") == "WARN"
        else "ok" if pre.get("overall") == "PASS"
        else "warn"
    )
    pre_label = f"preflight {pre.get('overall')}" if pre.get("available") else "preflight n/a"
    beads = data["beads"]
    beads_label = (
        f"bd {len(beads.get('in_progress') or [])}▶ {len(beads.get('ready') or [])}○ {len(beads.get('blocked') or [])}●"
        if beads.get("available")
        else "bd n/a"
    )
    convoys = data.get("convoys") or []
    open_cv = sum(1 for c in convoys if not c.get("landed") and (c.get("status") or "") != "closed")
    cv_label = f"cv {open_cv} open" if data.get("gastown_lite") else "cv n/a"
    stale_agents = data.get("stale_agents") or []
    banners = []
    if stale:
        banners.append(
            '<div class="banner">health.json looks stale vs health-latest.log (nopt-lib FAIL snapshot vs later PASS). Trust the log stanza until preflight rewrites the JSON.</div>'
        )
    if stale_agents:
        names = ", ".join(str(a.get("agent") or "?") for a in stale_agents)
        banners.append(
            f'<div class="banner">Witness-lite: stale heartbeat — {esc(names)} (45m).</div>'
        )
    stale_banner = "\n".join(banners)

    payload = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Neighbourhood</title>
<style>
:root {{
  --fg: var(--foreground, var(--ui-text-primary, #e8e4d9));
  --muted: var(--muted-foreground, var(--ui-text-tertiary, #9a9484));
  --accent: var(--accent, var(--ui-accent, #c9a227));
  --border: var(--border, var(--ui-stroke-secondary, #3a372f));
  --card: var(--card, color-mix(in srgb, var(--fg) 6%, transparent));
}}
* {{ box-sizing: border-box; }}
body {{
  color: var(--fg);
  line-height: 1.45;
}}
.bar {{
  display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline;
  padding: 10px 0 12px; border-bottom: 1px solid var(--border);
}}
.kicker {{ letter-spacing: .12em; text-transform: uppercase; font-size: 10px; color: var(--muted); }}
h1 {{ font-size: 18px; font-weight: 650; margin: 0; }}
.pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.pill {{
  border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
  font-size: 11px; color: var(--muted);
}}
.pill[data-tone=ok] {{ border-color: var(--accent); color: var(--fg); }}
.pill[data-tone=bad] {{ border-color: #c45c4a; color: #c45c4a; }}
.grid {{
  display: grid; grid-template-columns: minmax(180px, 22%) minmax(0, 1fr) minmax(220px, 30%);
  gap: 12px; margin-top: 12px;
}}
h2 {{ font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); margin: 0 0 8px; font-weight: 600; }}
.card {{
  border: 1px solid var(--border); border-radius: 8px; padding: 9px 10px; margin-bottom: 8px;
  background: var(--card);
}}
.card.unread {{ border-left: 2px solid var(--accent); }}
.row {{ display: flex; gap: 8px; align-items: center; justify-content: space-between; }}
.dot {{ width: 7px; height: 7px; border-radius: 99px; background: var(--accent); flex-shrink: 0; }}
.card[data-status=idle] .dot {{ background: var(--muted); }}
.muted {{ color: var(--muted); margin-top: 3px; }}
.tiny {{ color: var(--muted); font-size: 10px; margin-top: 4px; overflow-wrap: anywhere; }}
.empty {{ color: var(--muted); padding: 16px 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ text-align: left; padding: 5px 6px; border-bottom: 1px solid var(--border); vertical-align: top; }}
th {{ color: var(--muted); font-weight: 550; font-size: 10px; letter-spacing: .06em; text-transform: uppercase; }}
tr[data-ok=bad] .mark {{ color: #c45c4a; font-weight: 650; }}
tr[data-ok=ok] .mark {{ color: var(--accent); font-weight: 650; }}
tr[data-ok=warn] .mark {{ color: #d19a2e; font-weight: 650; }}
.pill[data-tone=warn] {{ border-color: #d19a2e; color: #d19a2e; }}
.banner {{
  border: 1px solid #c45c4a; color: #c45c4a; border-radius: 8px; padding: 8px 10px; margin-top: 10px; font-size: 12px;
}}
.work {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border);
}}
.dock {{
  margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border);
  display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 12px;
}}
.foot {{ margin-top: 14px; color: var(--muted); font-size: 11px; }}
@media (max-width: 720px) {{ .grid, .dock {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <header class="bar">
    <div>
      <div class="kicker">Neighbourhood</div>
      <h1>Ops board</h1>
    </div>
    <div class="pills">
      <span class="pill">snap {esc(data["built_at"])}</span>
      <span class="pill" data-tone="{health_tone}">MCP {esc("FAIL " + ",".join(fail) if fail else "verified PASS")}</span>
      <span class="pill" data-tone="{pre_tone}">{esc(pre_label)}</span>
      <span class="pill">{esc(beads_label)}</span>
      <span class="pill">{esc(cv_label)}</span>
      <span class="pill">{len(agents)} agents</span>
      <span class="pill">{data["unread_handoffs"]} unread</span>
      <span class="pill">courier {esc(courier["mode"])}</span>
    </div>
  </header>
  {stale_banner}
  <main class="grid">
    <section>
      <h2>Agents</h2>
      {agent_cards()}
    </section>
    <section>
      <h2>Convoys</h2>
      {convoy_cards()}
      <h2 style="margin-top:14px">Handoffs</h2>
      {handoff_cards()}
    </section>
    <section>
      <h2>MCP probes · {esc(health.get("source"))}</h2>
      <div class="tiny">{esc(health.get("checked_at") or "")}</div>
      {server_rows(health.get("servers") or [], "probes")}
      <h2 style="margin-top:14px">Preflight · {esc(pre.get("source") or "not run")}</h2>
      <div class="tiny">{esc(pre.get("checked_at") or "")}</div>
      {preflight_rows()}
      <h2 style="margin-top:14px">Beads · {esc(data["beads"].get("source") or "n/a")}</h2>
      {beads_rows()}
      <h2 style="margin-top:14px">Hub registry</h2>
      {mcp_rows()}
    </section>
  </main>
  <section class="dock">
    <div>
      <h2>Trail</h2>
      {trail_rows()}
    </div>
    <div>
      <h2>Formulas</h2>
      {formula_rows()}
    </div>
  </section>
  <section>
    <h2>Workstreams</h2>
    <div class="work">{work_cols()}</div>
  </section>
  <p class="foot">Read-only. Source: ~/.neighbourhood + ~/.mcp-hub/backups. Codex five-zone + Gas Town convoy/sling/formula/trail (no town). Rebuild: python dashboard/build.py</p>
  <script type="application/json" id="snapshot">{payload}</script>
</body>
</html>
"""


def write_snapshot(data: dict) -> None:
    DASH.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    (DASH / "snapshot.json").write_text(payload, encoding="utf-8")
    (DASH / "index.html").write_text(render(data), encoding="utf-8")
    plugin_dir = hermes_home() / "desktop-plugins" / "neighbourhood"
    if plugin_dir.is_dir() or (plugin_dir.parent / "cron-bulletin").is_dir():
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "snapshot.json").write_text(payload, encoding="utf-8")
    pkg = hermes_home() / "plugins" / "neighbourhood" / "dashboard"
    if pkg.is_dir():
        shutil.copy2(DASH / "snapshot.json", pkg / "snapshot.json")


def heartbeat(agent: str, task: str, note: str) -> None:
    path = BOARD / "status.json"
    data = read_json(path, {"schema_version": 1, "agents": {}})
    agents = data.setdefault("agents", {})
    agents[agent] = {
        "agent": agent,
        "status": "working",
        "current_task": task,
        "last_heartbeat": utcnow(),
        "note": note,
    }
    data["last_updated"] = utcnow()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def post_handoff(summary: str, payload: dict) -> Path:
    hid = str(uuid.uuid4())
    body = {
        "id": hid,
        "timestamp": utcnow(),
        "from_agent": "hermes",
        "to_agent": "ALL",
        "artifact_type": "result",
        "summary": summary,
        "payload": payload,
        "files_changed": [
            str(DASH / "index.html"),
            str(DASH / "build.py"),
            str(DASH / "STEAL.md"),
        ],
        "read_by": [],
    }
    path = BOARD / "handoffs" / f"{hid}.json"
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def self_check(data: dict, html: str) -> None:
    assert data["built_at"]
    assert "Neighbourhood" in html
    assert "snapshot" in html
    assert '<script type="application/json" id="snapshot">' in html
    json.loads(html.split('id="snapshot">', 1)[1].split("</script>", 1)[0])
    assert "convoys" in data
    assert "trail" in data
    assert "formulas" in data
    assert "Convoys" in html
    assert "Trail" in html
    print("self-check OK")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--heartbeat", action="store_true")
    p.add_argument("--handoff", action="store_true")
    args = p.parse_args(argv)
    data = snapshot()
    write_snapshot(data)
    html = (DASH / "index.html").read_text(encoding="utf-8-sig")
    self_check(data, html)
    if args.heartbeat:
        heartbeat(
            "hermes",
            "read-only neighbourhood dashboard v1",
            "HTML at ~/.neighbourhood/dashboard/index.html; Codex steal list posted.",
        )
        data = snapshot()
        write_snapshot(data)
    if args.handoff:
        path = post_handoff(
            "Dashboard v1 live: read-only HTML from status.json + handoffs + MCP health. Codex 5-zone steal list in dashboard/STEAL.md. Hermes kanban board `neighbourhood` created (Lucky5 default board untouched). Courier still dry-run.",
            {
                "dashboard": str(DASH / "index.html"),
                "kanban_board": "neighbourhood",
                "stale_health_json": data["health"].get("stale_file"),
            },
        )
        print(f"handoff {path.name}")
    print(f"wrote {DASH / 'index.html'}")
    print(f"agents={len(data['agents'])} handoffs={len(data['handoffs'])} unread={data['unread_handoffs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
