"""Worker integration test using a mock yt-dlp.

Boots worker.sh in the background with YTDLP_BIN=tests/fixtures/fake-ytdlp.sh,
enqueues two jobs, asserts both reach state=done with files on disk in FIFO
order, then SIGTERMs the worker and asserts the PID file is removed.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKER = REPO / "agent-b" / "worker.sh"
QUEUE_PY = REPO / "agent-b" / "queue.py"
FAKE_YTDLP = REPO / "tests" / "fixtures" / "fake-ytdlp.sh"


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "agent-b"
    d.mkdir()
    shutil.copy(QUEUE_PY, d / "queue.py")
    shutil.copy(WORKER, d / "worker.sh")
    os.chmod(d / "queue.py", 0o755)
    os.chmod(d / "worker.sh", 0o755)
    return d


def _q(workdir: Path, *args: str) -> dict:
    p = subprocess.run([sys.executable, str(workdir / "queue.py"), *args],
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _wait_state(workdir: Path, job_id: str, want: str, timeout: float = 8) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = _q(workdir, "status")
        for j in snap["jobs"]:
            if j["id"] == job_id and j["state"] == want:
                return j
        time.sleep(0.2)
    raise AssertionError(f"timeout waiting for {job_id} to reach {want}")


def test_worker_processes_jobs_in_fifo_with_mock(workdir: Path) -> None:
    env = os.environ.copy()
    env["YTDLP_BIN"] = str(FAKE_YTDLP)
    env["QUEUE_DIR"] = str(workdir)
    env["DOWNLOAD_DIR"] = str(workdir / "downloads")
    env["STATE_DIR"] = str(workdir / "state")

    proc = subprocess.Popen(["bash", str(workdir / "worker.sh")], env=env)
    try:
        time.sleep(0.5)
        a = _q(workdir, "enqueue", "https://example.com/a.mp4")["id"]
        b = _q(workdir, "enqueue", "https://example.com/b.mp4")["id"]

        ja = _wait_state(workdir, a, "done")
        jb = _wait_state(workdir, b, "done")

        assert ja["progress"] == 100 and jb["progress"] == 100
        assert Path(ja["file"]).exists()
        assert Path(jb["file"]).exists()
        # FIFO: a finished no later than b
        assert ja["updatedAt"] <= jb["updatedAt"]
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

    pid_file = workdir / "state" / "worker.pid"
    assert not pid_file.exists(), "worker should remove its PID file on exit"


def test_worker_marks_failed_on_ytdlp_error(workdir: Path, tmp_path: Path) -> None:
    failing = tmp_path / "failing-ytdlp.sh"
    failing.write_text("#!/usr/bin/env bash\nexit 1\n")
    os.chmod(failing, 0o755)

    env = os.environ.copy()
    env["YTDLP_BIN"] = str(failing)
    env["QUEUE_DIR"] = str(workdir)
    env["DOWNLOAD_DIR"] = str(workdir / "downloads")
    env["STATE_DIR"] = str(workdir / "state")

    proc = subprocess.Popen(["bash", str(workdir / "worker.sh")], env=env)
    try:
        time.sleep(0.5)
        jid = _q(workdir, "enqueue", "https://example.com/x")["id"]
        j = _wait_state(workdir, jid, "failed")
        assert j["error"]
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
