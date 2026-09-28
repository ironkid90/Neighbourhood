#!/usr/bin/env python3
"""Offline smoke tests for the Neighbourhood product repo.

Does not need a live board, bd CLI, or network. Install.cmd runs this
before copying is considered good.
"""
from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global FAIL
    tone = "PASS" if ok else "FAIL"
    if not ok:
        FAIL += 1
    print(f"{tone:7} {name:24} {detail}")


def python_files() -> list[Path]:
    skip = {"__pycache__"}
    out = []
    for path in ROOT.rglob("*.py"):
        if any(part in skip or part.startswith(".") for part in path.parts):
            continue
        out.append(path)
    return out


def compile_all() -> None:
    for path in python_files():
        try:
            py_compile.compile(str(path), doraise=True)
            check(f"compile:{path.relative_to(ROOT)}", True)
        except py_compile.PyCompileError as exc:
            check(f"compile:{path.relative_to(ROOT)}", False, str(exc)[:200])


def run_help(script: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(script), "-h"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    check(f"help:{script.name}", proc.returncode == 0, f"exit={proc.returncode}")


def test_board_env() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["NHOOD_HOME"] = tmp
        code = (
            "import importlib.util, os, sys\n"
            "from pathlib import Path\n"
            f"p = Path(r'{ROOT / 'tools' / 'nhood.py'}')\n"
            "spec = importlib.util.spec_from_file_location('nhood', p)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(mod.BOARD)\n"
            "assert Path(os.environ['NHOOD_HOME']) == Path(mod.BOARD)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        check("nhood NHOOD_HOME", proc.returncode == 0, (proc.stdout or proc.stderr or "")[:160].strip())


def test_plugin_portable() -> None:
    js = (ROOT / "desktop-plugin" / "plugin.js").read_text(encoding="utf-8")
    check("plugin no kapo_ path", "kapo_" not in js and "HTML_PATH" not in js)
    check("plugin lastSnapshot", "lastSnapshot" in js and "htmlPathFromSnapshot" in js)


def test_catalog() -> None:
    path = ROOT / "catalog" / "atlas.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    check("catalog schema", data.get("schema_version") == 1)
    policy = data.get("policy") or {}
    check("catalog control_plane", policy.get("control_plane") == "neighbourhood")
    check("catalog memory", policy.get("memory") == "mem0")
    check("catalog mcp", policy.get("mcp") == "mcp-hub")
    never = policy.get("never_auto") or []
    check("catalog never mcp.json", any("mcp.json" in x for x in never))
    allowed = {"have", "install", "optional", "gated", "skip"}
    modules = data.get("modules") or []
    check("catalog modules", len(modules) >= 10, f"count={len(modules)}")
    ids = []
    for mod in modules:
        mid = mod.get("id")
        ids.append(mid)
        check(f"catalog tier:{mid}", mod.get("tier") in allowed, str(mod.get("tier")))
    check("catalog unique ids", len(ids) == len(set(ids)))
    by_id = {m["id"]: m for m in modules}
    check("catalog superpowers install", by_id.get("superpowers", {}).get("tier") == "install")
    check("catalog mc gated", by_id.get("mission-control", {}).get("tier") == "gated")
    check("catalog paperclip optional", by_id.get("paperclip-adapter", {}).get("tier") == "optional")
    cases = data.get("use_cases") or []
    check("catalog 14 use-cases", len(cases) == 14, f"count={len(cases)}")


def test_no_secrets() -> None:
    real_cfg = ROOT / "courier" / "courier-config.json"
    check("no courier-config.json", not real_cfg.is_file(), "example only")
    example = json.loads((ROOT / "courier" / "courier-config.example.json").read_text(encoding="utf-8"))
    check("example token empty", not example.get("token") and not example.get("chat_id"))


def test_product_layout() -> None:
    required = [
        "Install.cmd",
        "Start.cmd",
        "Doctor.cmd",
        "Runtime.cmd",
        "dashboard/build.py",
        "tools/nhood.py",
        "desktop-plugin/plugin.js",
        "formulas/nhood-feature.formula.toml",
        "templates/RULES.md",
        "templates/status.json",
        "scripts/install.ps1",
        "scripts/runtime.ps1",
        "catalog/atlas.json",
        "docs/ATLAS_RUNTIME.md",
        "courier/neighbourhood_courier.py",
    ]
    for rel in required:
        path = ROOT / rel
        check(f"layout:{rel}", path.is_file())


def main() -> int:
    compile_all()
    run_help(ROOT / "tools" / "nhood.py")
    run_help(ROOT / "dashboard" / "build.py")
    test_board_env()
    test_plugin_portable()
    test_no_secrets()
    test_product_layout()
    test_catalog()
    print(f"{'FAIL' if FAIL else 'PASS'} smoke ({FAIL} failure(s))")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
