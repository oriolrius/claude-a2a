.PHONY: install run-a run-b stop

install:
	uv sync

run-a:
	uv run python -m agent-a.server

run-b:
	uv run python -m agent-b.server

# Convenience: launch both A2A servers in background; skip if port already listening
up:
	@if ss -ltn 'sport = :9001' | grep -q 9001; then \
		echo "agent-a :9001 already running (skip)"; \
	else \
		uv run python agent-a/server.py >/tmp/a2a-9001.log 2>&1 & echo $$! > .pid-a; \
		echo "agent-a :9001 (pid $$(cat .pid-a))"; \
	fi
	@if ss -ltn 'sport = :9002' | grep -q 9002; then \
		echo "agent-b :9002 already running (skip)"; \
	else \
		uv run python agent-b/server.py >/tmp/a2a-9002.log 2>&1 & echo $$! > .pid-b; \
		echo "agent-b :9002 (pid $$(cat .pid-b))"; \
	fi

down:
	-@kill $$(cat .pid-a) 2>/dev/null; rm -f .pid-a
	-@kill $$(cat .pid-b) 2>/dev/null; rm -f .pid-b

# Smoke test: send hello from A to B and poll
smoke:
	uv run python smoke.py
