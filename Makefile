.PHONY: install run-a run-b stop

install:
	uv sync

run-a:
	uv run python -m agent-a.server

run-b:
	uv run python -m agent-b.server

# Convenience: launch both A2A servers in background
up:
	uv run python agent-a/server.py & echo $$! > .pid-a
	uv run python agent-b/server.py & echo $$! > .pid-b
	@echo "agent-a :9001 (pid $$(cat .pid-a))"
	@echo "agent-b :9002 (pid $$(cat .pid-b))"

down:
	-@kill $$(cat .pid-a) 2>/dev/null; rm -f .pid-a
	-@kill $$(cat .pid-b) 2>/dev/null; rm -f .pid-b

# Smoke test: send hello from A to B and poll
smoke:
	uv run python smoke.py
