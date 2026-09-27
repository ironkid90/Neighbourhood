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
    check(
        "plugin dock fields",
        all(tok in js for tok in ("nhood-dock", "convoys", "trail", "formulas", "beadsLabel")),
    )


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
        "Snapshot.cmd",
        "dashboard/build.py",
        "tools/nhood.py",
        "desktop-plugin/plugin.js",
        "formulas/nhood-feature.formula.toml",
        "templates/RULES.md",
        "templates/status.json",
        "scripts/install.ps1",
        "scripts/doctor.ps1",
        "scripts/common.ps1",
        "scripts/uninstall.ps1",
        "preflight/preflight.ps1",
        "courier/neighbourhood_courier.py",
        "hermes-plugin/dashboard/plugin_api.py",
    ]
    for rel in required:
        path = ROOT / rel
        check(f"layout:{rel}", path.is_file())


def test_formula() -> None:
    path = ROOT / "formulas" / "nhood-feature.formula.toml"
    with path.open("rb") as fh:
        data = __import__("tomllib").load(fh)
    check("formula name", data.get("formula") == "nhood-feature")
    feat = (data.get("vars") or {}).get("feature") or {}
    check("formula feature required", bool(feat.get("required")))
    steps = [s.get("id") for s in (data.get("steps") or []) if isinstance(s, dict) and s.get("id")]
    check("formula steps", steps == ["design", "implement", "verify"], ",".join(steps))


def test_hermes_home_walks_profile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "hermes"
        (root / "desktop-plugins").mkdir(parents=True)
        profile = root / "profiles" / "default"
        profile.mkdir(parents=True)
        env = os.environ.copy()
        env["HERMES_HOME"] = str(profile)
        code = (
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"p = Path(r'{ROOT / 'dashboard' / 'build.py'}')\n"
            "spec = importlib.util.spec_from_file_location('nhood_build', p)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(mod.hermes_home())\n"
            f"assert Path(mod.hermes_home()).resolve() == Path(r'{root}').resolve()\n"
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
        check(
            "hermes_home walks profile",
            proc.returncode == 0,
            (proc.stdout or proc.stderr or "")[:200].strip(),
        )


def test_courier_once() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        board = Path(tmp)
        handoffs = board / "handoffs"
        handoffs.mkdir()
        human = {
            "id": "human-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "from_agent": "hermes",
            "to_agent": "human",
            "artifact_type": "result",
            "summary": "ping-human",
            "payload": {},
            "files_changed": [],
            "read_by": [],
        }
        everyone = dict(human, id="all-1", to_agent="ALL", summary="ping-all")
        (handoffs / "human-1.json").write_text(json.dumps(human), encoding="utf-8")
        (handoffs / "all-1.json").write_text(json.dumps(everyone), encoding="utf-8")
        env = os.environ.copy()
        env["BOARD_DIR"] = str(board)
        env["NHOOD_HOME"] = str(board)
        env.pop("TELEGRAM_BOT_TOKEN", None)
        env.pop("TELEGRAM_CHAT_ID", None)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "courier" / "neighbourhood_courier.py"), "--once"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            cwd=str(ROOT),
        )
        out = proc.stdout or ""
        check("courier --once", proc.returncode == 0, (out or proc.stderr or "")[:160].strip())
        check("courier relays human", "ping-human" in out)
        check("courier skips ALL", "ping-all" not in out)


def test_nhood_helpers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["NHOOD_HOME"] = tmp
        code = (
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"p = Path(r'{ROOT / 'tools' / 'nhood.py'}')\n"
            "spec = importlib.util.spec_from_file_location('nhood', p)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "assert mod.subst('Mol: {{feature}}', {'feature': 'refinery'}) == 'Mol: refinery'\n"
            "ids = mod.track_ids_from_deps([{'depends_on_id': 'nhood-abc', 'issue_id': 'nhood-b4y'}])\n"
            "assert ids == ['nhood-abc'], ids\n"
            "print('ok')\n"
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
        check("nhood subst/deps", proc.returncode == 0, (proc.stdout or proc.stderr or "")[:160].strip())


def main() -> int:
    compile_all()
    run_help(ROOT / "tools" / "nhood.py")
    run_help(ROOT / "dashboard" / "build.py")
    run_help(ROOT / "courier" / "neighbourhood_courier.py")
    test_board_env()
    test_plugin_portable()
    test_no_secrets()
    test_product_layout()
    test_formula()
    test_hermes_home_walks_profile()
    test_courier_once()
    test_nhood_helpers()
    print(f"{'FAIL' if FAIL else 'PASS'} smoke ({FAIL} failure(s))")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
