"""Unit tests for agent-b/queue.py — single-process and concurrent."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
QUEUE_PY = REPO / "agent-b" / "queue.py"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """Run queue.py against an isolated state dir via PYTHONPATH/cwd trick.
    queue.py hardcodes its state path relative to its file. To isolate per-test
    we copy queue.py into tmp_path/agent-b/ so its sibling state dir is fresh.
    """
    target_dir = tmp_path / "agent-b"
    target_dir.mkdir()
    target = target_dir / "queue.py"
    target.write_bytes(QUEUE_PY.read_bytes())
    os.chmod(target, 0o755)
    e = os.environ.copy()
    return {"e": e, "queue": str(target)}


def _q(env: dict, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, env["queue"], *args],
                       capture_output=True, text=True, env=env["e"])
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def test_enqueue_returns_id_and_position(env) -> None:
    rc, out, _ = _q(env, "enqueue", "https://x/y")
    assert rc == 0
    data = json.loads(out)
    assert data["id"]
    assert data["position"] == 1
    assert data["job"]["state"] == "queued"


def test_status_full_and_single(env) -> None:
    rc, out, _ = _q(env, "enqueue", "https://x/a")
    job_id = json.loads(out)["id"]
    rc, out, _ = _q(env, "status")
    assert rc == 0 and len(json.loads(out)["jobs"]) == 1
    rc, out, _ = _q(env, "status", job_id)
    assert json.loads(out)["url"] == "https://x/a"


def test_status_unknown_id(env) -> None:
    rc, out, _ = _q(env, "status", "nope")
    assert rc != 0
    assert json.loads(out)["error"]


def test_cancel_only_queued(env) -> None:
    rc, out, _ = _q(env, "enqueue", "https://x/a")
    job_id = json.loads(out)["id"]
    rc, out, _ = _q(env, "cancel", job_id)
    assert rc == 0 and json.loads(out)["state"] == "canceled"
    rc, out, _ = _q(env, "cancel", job_id)
    assert rc != 0


def test_next_pops_in_fifo_order(env) -> None:
    a = json.loads(_q(env, "enqueue", "https://x/1")[1])["id"]
    b = json.loads(_q(env, "enqueue", "https://x/2")[1])["id"]
    rc, out, _ = _q(env, "next")
    first = json.loads(out)["id"]
    rc, out, _ = _q(env, "next")
    second = json.loads(out)["id"]
    assert first == a and second == b


def test_next_returns_empty_when_no_queued(env) -> None:
    rc, out, _ = _q(env, "next")
    assert rc == 0 and out == ""


def test_mark_updates_fields(env) -> None:
    job_id = json.loads(_q(env, "enqueue", "https://x/a")[1])["id"]
    _q(env, "next")
    rc, out, _ = _q(env, "mark", job_id, "done", "--file", "/tmp/f.mp4", "--progress", "100")
    data = json.loads(out)
    assert data["state"] == "done"
    assert data["file"] == "/tmp/f.mp4"
    assert data["progress"] == 100


def test_clear_done_purges_terminal_states(env) -> None:
    a = json.loads(_q(env, "enqueue", "https://x/1")[1])["id"]
    b = json.loads(_q(env, "enqueue", "https://x/2")[1])["id"]
    _q(env, "next"); _q(env, "mark", a, "done")
    _q(env, "cancel", b)
    rc, out, _ = _q(env, "clear-done")
    assert json.loads(out)["removed"] == 2
    rc, out, _ = _q(env, "status")
    assert json.loads(out)["jobs"] == []


def test_concurrent_enqueue_no_lost_writes(env) -> None:
    """Spawn 20 parallel enqueue subprocesses; expect all 20 jobs persisted."""
    def one(i: int) -> None:
        _q(env, "enqueue", f"https://x/{i}")

    with ThreadPoolExecutor(max_workers=20) as ex:
        list(ex.map(one, range(20)))

    rc, out, _ = _q(env, "status")
    jobs = json.loads(out)["jobs"]
    assert len(jobs) == 20
    urls = {j["url"] for j in jobs}
    assert urls == {f"https://x/{i}" for i in range(20)}
