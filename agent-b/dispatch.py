#!/usr/bin/env python3
"""Single entry point used by agent-b's Claude session.

Takes the raw inbox-message text, parses it, runs the right queue.py
subcommand, and prints a structured JSON envelope to stdout. The Claude
session in agent-b calls this once per inbox task and forwards the
stdout verbatim through `a2a_respond`.

Envelope:
    {"command": "download" | "status" | "cancel",
     "ok": true | false,
     "result": <queue.py output> | null,
     "error": "..." | null}
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "queue.py"

# Patterns
RE_DOWNLOAD = re.compile(
    r"""^\s*download\s+
        (?P<url>\S+)
        (?:\s+format\s+(?P<fmt>\S.*?))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)
RE_STATUS = re.compile(r"^\s*status(?:\s+(?P<id>\S+))?\s*$", re.IGNORECASE)
RE_CANCEL = re.compile(r"^\s*cancel\s+(?P<id>\S+)\s*$", re.IGNORECASE)


def _envelope(command: str, ok: bool, result: Any = None,
              error: str | None = None) -> str:
    return json.dumps(
        {"command": command, "ok": ok, "result": result, "error": error},
        indent=2,
    )


def _run_queue(*args: str) -> tuple[bool, Any, str | None]:
    proc = subprocess.run(
        [sys.executable, str(QUEUE), *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        # queue.py prints JSON {"error": "..."} on failure
        try:
            data = json.loads(proc.stdout or "{}")
            return False, None, data.get("error") or proc.stderr.strip() or "queue error"
        except json.JSONDecodeError:
            return False, None, proc.stderr.strip() or "queue error"
    try:
        return True, json.loads(proc.stdout), None
    except json.JSONDecodeError:
        return True, proc.stdout.strip(), None


def dispatch(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return _envelope("?", False, error="empty command")

    m = RE_DOWNLOAD.match(text)
    if m:
        args = ["enqueue", m.group("url")]
        if m.group("fmt"):
            args += ["--format", m.group("fmt")]
        ok, result, err = _run_queue(*args)
        return _envelope("download", ok, result, err)

    m = RE_STATUS.match(text)
    if m:
        args = ["status"] + ([m.group("id")] if m.group("id") else [])
        ok, result, err = _run_queue(*args)
        return _envelope("status", ok, result, err)

    m = RE_CANCEL.match(text)
    if m:
        ok, result, err = _run_queue("cancel", m.group("id"))
        return _envelope("cancel", ok, result, err)

    return _envelope(
        "?", False,
        error=(f"unrecognized command: {text!r}. "
               "Expected: 'download <url> [format <fmt>]', 'status [<id>]', "
               "or 'cancel <id>'."),
    )


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    sys.stdout.write(dispatch(text))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
