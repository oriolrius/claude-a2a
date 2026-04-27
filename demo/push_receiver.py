"""Tiny webhook receiver for the push-notification demo.

Runs on the port given via $PORT (default 9090). Logs every incoming push
event to stdout and to demo/push.log. Intended to be started in the
background by run-push.sh.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request

LOG_FILE = Path(__file__).resolve().parent / "push.log"
app = FastAPI()


@app.post("/hook")
async def hook(req: Request) -> dict:
    body = await req.json()
    line = json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "token": req.headers.get("x-a2a-notification-token"),
        "event": body,
    })
    sys.stdout.write(line + "\n"); sys.stdout.flush()
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")
    return {"ok": True}


def main() -> None:
    port = int(os.environ.get("PORT", "9090"))
    LOG_FILE.write_text("")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
