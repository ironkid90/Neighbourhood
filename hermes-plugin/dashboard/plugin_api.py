"""Read-only Neighbourhood snapshot for the desktop / dashboard plugin.

Imported only when `neighbourhood` is in config.yaml plugins.enabled.
Does not write mcp.json, config.yaml, or secrets.
"""
from __future__ import annotations

import runpy
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

def _board() -> Path:
    return Path(
        __import__("os").environ.get("NHOOD_HOME")
        or __import__("os").environ.get("NEIGHBOURHOOD_BOARD_DIR")
        or (Path.home() / ".neighbourhood")
    )


_BUILD = _board() / "dashboard" / "build.py"


def _load_build():
    if not _BUILD.is_file():
        raise FileNotFoundError(str(_BUILD))
    return runpy.run_path(str(_BUILD), run_name="nhood_build")


@router.get("/snapshot")
def snapshot_endpoint():
    try:
        ns = _load_build()
        data = ns["snapshot"]()
        ns["write_snapshot"](data)
        return data
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface the build error to the pane
        raise HTTPException(status_code=500, detail=type(exc).__name__) from exc


@router.get("/status")
def status_endpoint():
    return {
        "ok": _BUILD.is_file(),
        "build": str(_BUILD),
        "read_only": True,
    }
