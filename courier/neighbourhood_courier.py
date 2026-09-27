#!/usr/bin/env python3
"""
neighbourhood-courier — the Telegram courier for the neighbourhood board.

Polls the board's handoffs/ directory for messages addressed to `human`,
relays them to a Telegram chat, and posts the human's replies back to the
board as handoffs from `telegram-courier`.

Design rules (same as the board):
- Works on plain files; the MCP server does NOT need to be running.
- Never blocks the board: all errors are logged, never raised.
- Without a token it runs in dry-run mode (prints what it would send).

Config (env or courier-config.json next to this script):
    TELEGRAM_BOT_TOKEN   bot token from @BotFather
    TELEGRAM_CHAT_ID     chat to relay to
    BOARD_DIR            path to the neighbourhood board dir
    POLL_SECONDS         poll interval (default 30)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
COURIER_NAME = "telegram-courier"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    cfg = {
        "token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "board_dir": os.environ.get("BOARD_DIR")
        or os.environ.get("NHOOD_HOME")
        or os.environ.get("NEIGHBOURHOOD_BOARD_DIR")
        or str(Path.home() / ".neighbourhood"),
    }
    cfg_file = Path(__file__).with_name("courier-config.json")
    if cfg_file.exists():
        try:
            file_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            for k in cfg:
                if file_cfg.get(k):
                    cfg[k] = file_cfg[k]
        except Exception as e:  # noqa: BLE001 - courier never dies on config errors
            log(f"config file unreadable: {e}")
    return cfg


def log(msg: str) -> None:
    print(f"[{utcnow()}] {COURIER_NAME}: {msg}", flush=True)


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.dry_run = not (token and chat_id)
        if self.dry_run:
            log("no token/chat_id — DRY RUN (messages printed, not sent)")
        self.offset = 0

    def send(self, text: str) -> bool:
        if self.dry_run:
            log(f"DRY-RUN send -> {text[:120]}")
            return True
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body = json.dumps({"chat_id": self.chat_id, "text": text[:4096]}).encode()
        try:
            with urllib.request.urlopen(url, data=body, timeout=15) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError) as e:
            log(f"send failed: {e}")
            return False

    def poll_replies(self) -> list[str]:
        if self.dry_run:
            return []
        url = (
            f"https://api.telegram.org/bot{self.token}/getUpdates"
            f"?offset={self.offset}&timeout=0"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError) as e:
            log(f"poll failed: {e}")
            return []
        replies = []
        for upd in data.get("result", []):
            self.offset = max(self.offset, upd["update_id"] + 1)
            msg = upd.get("message", {})
            if str(msg.get("chat", {}).get("id")) == str(self.chat_id):
                text = msg.get("text", "").strip()
                if text:
                    replies.append(text)
        return replies


class Board:
    """Plain-file access to the neighbourhood board. No MCP required."""

    def __init__(self, board_dir: str):
        self.dir = Path(board_dir)
        self.handoffs = self.dir / "handoffs"
        self.handoffs.mkdir(parents=True, exist_ok=True)
        self.seen_file = self.dir / ".courier-seen.json"
        self.seen: set[str] = set()
        self._load_seen()

    def _load_seen(self) -> None:
        try:
            if self.seen_file.exists():
                self.seen = set(json.loads(self.seen_file.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            self.seen = set()

    def _save_seen(self) -> None:
        try:
            self.seen_file.write_text(json.dumps(sorted(self.seen)), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log(f"could not persist seen-set: {e}")

    def unread_for_human(self) -> list[dict]:
        out = []
        for f in sorted(self.handoffs.glob("*.json")):
            try:
                h = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if h.get("id") in self.seen:
                continue
            if h.get("to_agent") in ("human", "ALL"):
                out.append(h)
        return out

    def mark_seen(self, handoff_id: str) -> None:
        self.seen.add(handoff_id)
        self._save_seen()

    def post(self, from_agent: str, to_agent: str, artifact_type: str, summary: str) -> None:
        import uuid
        handoff = {
            "id": str(uuid.uuid4()),
            "timestamp": utcnow(),
            "from_agent": from_agent,
            "to_agent": to_agent,
            "artifact_type": artifact_type,
            "summary": summary,
            "payload": {},
            "files_changed": [],
            "read_by": [],
        }
        f = self.handoffs / f"{handoff['id']}.json"
        f.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
        log(f"posted reply to board: {summary[:80]}")


def main() -> None:
    cfg = load_config()
    board_path = Path(cfg["board_dir"])
    if not board_path.is_dir():
        log(f"board dir missing: {board_path}; exiting")
        sys.exit(1)

    tg = Telegram(cfg["token"], cfg["chat_id"])
    board = Board(cfg["board_dir"])
    log(f"watching board at {board.dir} every {POLL_SECONDS}s")
    tg.send("📡 neighbourhood courier online. I'll relay handoffs addressed to you.")

    while True:
        try:
            for h in board.unread_for_human():
                text = (
                    f"🏘 <{h.get('from_agent','?')}> [{h.get('artifact_type','?')}]\n"
                    f"{h.get('summary','')}"
                )
                if tg.send(text):
                    board.mark_seen(h["id"])

            for reply in tg.poll_replies():
                board.post(COURIER_NAME, "ALL", "human_reply", reply)
        except Exception as e:  # noqa: BLE001 - the courier must never die
            log(f"loop error (continuing): {e}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
