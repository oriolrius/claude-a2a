#!/usr/bin/env python3
"""Tiny FIFO queue manager backed by a JSON file with flock.

Subcommands (all read/modify queue.json atomically):
    enqueue <url> [--format FMT]   add job, print {id, position}
    status [id]                    print queue snapshot or single job
    cancel <id>                    mark job canceled (only if queued)
    next                           pop next queued job → set running, print json
    mark <id> <state> [--file F] [--error E] [--progress P]
                                   update an existing job
    clear-done                     remove jobs in done|failed|canceled
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

QUEUE_FILE = Path(__file__).resolve().parent / "state" / "queue.json"
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load(fp) -> dict[str, Any]:
    fp.seek(0)
    raw = fp.read()
    if not raw:
        return {"jobs": []}
    return json.loads(raw)


def _save(fp, data: dict[str, Any]) -> None:
    fp.seek(0)
    fp.truncate()
    json.dump(data, fp, indent=2)
    fp.flush()


def _open_locked():
    fp = open(QUEUE_FILE, "a+")
    fcntl.flock(fp, fcntl.LOCK_EX)
    return fp


def cmd_enqueue(args) -> None:
    job = {
        "id": str(uuid.uuid4())[:8],
        "url": args.url,
        "format": args.format,
        "state": "queued",
        "progress": 0,
        "file": None,
        "error": None,
        "createdAt": time.time(),
        "updatedAt": time.time(),
    }
    with _open_locked() as fp:
        data = _load(fp)
        data["jobs"].append(job)
        _save(fp, data)
        position = sum(1 for j in data["jobs"] if j["state"] == "queued")
    print(json.dumps({"id": job["id"], "position": position, "job": job}, indent=2))


def cmd_status(args) -> None:
    with _open_locked() as fp:
        data = _load(fp)
    if args.id:
        for j in data["jobs"]:
            if j["id"] == args.id:
                print(json.dumps(j, indent=2))
                return
        print(json.dumps({"error": "not found"})); sys.exit(1)
    print(json.dumps(data, indent=2))


def cmd_cancel(args) -> None:
    with _open_locked() as fp:
        data = _load(fp)
        for j in data["jobs"]:
            if j["id"] == args.id and j["state"] == "queued":
                j["state"] = "canceled"
                j["updatedAt"] = time.time()
                _save(fp, data)
                print(json.dumps(j, indent=2))
                return
        print(json.dumps({"error": "not cancelable"})); sys.exit(1)


def cmd_next(args) -> None:
    with _open_locked() as fp:
        data = _load(fp)
        for j in data["jobs"]:
            if j["state"] == "queued":
                j["state"] = "running"
                j["updatedAt"] = time.time()
                _save(fp, data)
                print(json.dumps(j))
                return
    # nothing
    print("")


def cmd_mark(args) -> None:
    with _open_locked() as fp:
        data = _load(fp)
        for j in data["jobs"]:
            if j["id"] == args.id:
                j["state"] = args.state
                if args.file is not None:
                    j["file"] = args.file
                if args.error is not None:
                    j["error"] = args.error
                if args.progress is not None:
                    j["progress"] = args.progress
                j["updatedAt"] = time.time()
                _save(fp, data)
                print(json.dumps(j, indent=2))
                return
        print(json.dumps({"error": "not found"})); sys.exit(1)


def cmd_clear_done(args) -> None:
    with _open_locked() as fp:
        data = _load(fp)
        before = len(data["jobs"])
        data["jobs"] = [j for j in data["jobs"]
                        if j["state"] not in ("done", "failed", "canceled")]
        _save(fp, data)
        print(json.dumps({"removed": before - len(data["jobs"])}))


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("enqueue"); a.add_argument("url"); a.add_argument("--format", default=None)
    a.set_defaults(func=cmd_enqueue)

    a = sub.add_parser("status"); a.add_argument("id", nargs="?", default=None)
    a.set_defaults(func=cmd_status)

    a = sub.add_parser("cancel"); a.add_argument("id"); a.set_defaults(func=cmd_cancel)
    a = sub.add_parser("next"); a.set_defaults(func=cmd_next)

    a = sub.add_parser("mark"); a.add_argument("id"); a.add_argument("state")
    a.add_argument("--file", default=None); a.add_argument("--error", default=None)
    a.add_argument("--progress", type=int, default=None)
    a.set_defaults(func=cmd_mark)

    a = sub.add_parser("clear-done"); a.set_defaults(func=cmd_clear_done)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
