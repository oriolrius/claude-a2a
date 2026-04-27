"""Agent B — A2A HTTP server on :9002."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.a2a import AgentCard, TaskStore, make_app, serve_blocking

CARD = AgentCard(
    name="agent-b",
    description="Claude Code agent B. Speaks A2A, exposes peer access via MCP.",
    url="http://127.0.0.1:9002/",
    skills=[{
        "id": "chat",
        "name": "chat",
        "description": "Free-form text exchange with peer agents.",
        "tags": ["text"],
    }],
)

if __name__ == "__main__":
    serve_blocking(make_app(CARD, TaskStore()), host="127.0.0.1", port=9002)
