"""Tests for agent-b/dispatch.py command parser + envelope shape."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "agent-b"


@pytest.fixture
def sandbox(tmp_path: Path):
    """Copy dispatch.py + queue.py to a tmp dir so state is isolated."""
    dst = tmp_path / "agent-b"
    dst.mkdir()
    for name in ("queue.py", "dispatch.py"):
        target = dst / name
        target.write_bytes((SRC / name).read_bytes())
        os.chmod(target, 0o755)
    return dst


def _dispatch(sandbox: Path, text: str) -> dict:
    p = subprocess.run(
        [sys.executable, str(sandbox / "dispatch.py"), text],
        capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_download_basic(sandbox) -> None:
    env = _dispatch(sandbox, "download https://x/y.mp4")
    assert env["command"] == "download"
    assert env["ok"] is True
    assert env["result"]["job"]["url"] == "https://x/y.mp4"


def test_download_with_format(sandbox) -> None:
    env = _dispatch(sandbox, "download https://x/y.mp4 format best[height<=240]")
    assert env["ok"] is True
    assert env["result"]["job"]["format"] == "best[height<=240]"


def test_status_full_and_single(sandbox) -> None:
    enq = _dispatch(sandbox, "download https://x/a")
    jid = enq["result"]["id"]
    full = _dispatch(sandbox, "status")
    assert full["ok"] and len(full["result"]["jobs"]) == 1
    one = _dispatch(sandbox, f"status {jid}")
    assert one["ok"] and one["result"]["url"] == "https://x/a"


def test_status_unknown_id_is_error(sandbox) -> None:
    env = _dispatch(sandbox, "status nope")
    assert env["ok"] is False and env["error"]


def test_cancel(sandbox) -> None:
    enq = _dispatch(sandbox, "download https://x/a")
    jid = enq["result"]["id"]
    env = _dispatch(sandbox, f"cancel {jid}")
    assert env["ok"] and env["result"]["state"] == "canceled"


def test_unknown_command(sandbox) -> None:
    env = _dispatch(sandbox, "delete everything")
    assert env["ok"] is False
    assert env["command"] == "?"
    assert "unrecognized" in env["error"]


def test_empty_command(sandbox) -> None:
    env = _dispatch(sandbox, "")
    assert env["ok"] is False
    assert "empty" in env["error"]


def test_case_insensitive_keywords(sandbox) -> None:
    env = _dispatch(sandbox, "DOWNLOAD https://x/a")
    assert env["ok"] is True
