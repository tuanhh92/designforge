# DesignForge MVP — developer commands. Requires Python 3.12+, Node 20+, Docker (for Postgres).
PY      ?= python3.13
VENV    := .venv
BIN     := $(VENV)/bin
ENV     := set -a; [ -f .env ] && . ./.env; set +a;

.PHONY: setup env db-up db-down db-brew migrate api worker web bridge-fake bridge-setup bridge-rbz dev stop status test

setup: env
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e "python[ai,mcp]" -e "apps/api[dev]"
	cd apps/web && npm install

env:
	@[ -f .env ] || (cp .env.example .env && chmod 600 .env)  # API keys go here: owner-only
	@[ -f apps/web/.env.local ] || echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > apps/web/.env.local

db-up:
	docker compose -f infra/docker-compose.yml up -d --wait

db-down:
	docker compose -f infra/docker-compose.yml down

# Postgres without Docker (macOS): Homebrew Postgres 16 + the user/databases .env expects.
db-brew:
	brew list postgresql@16 >/dev/null 2>&1 || brew install postgresql@16
	brew services start postgresql@16
	@for i in $$(seq 1 20); do /opt/homebrew/opt/postgresql@16/bin/pg_isready -q && break; sleep 1; done
	/opt/homebrew/opt/postgresql@16/bin/psql -d postgres -qc "DO $$$$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='designforge') THEN CREATE ROLE designforge LOGIN PASSWORD 'designforge' CREATEDB; END IF; END $$$$;"
	-/opt/homebrew/opt/postgresql@16/bin/createdb -O designforge designforge 2>/dev/null
	-/opt/homebrew/opt/postgresql@16/bin/createdb -O designforge designforge_test 2>/dev/null

# Whole stack in the background (logs in var/log/); `make stop` to stop, `make status` to check.
dev:
	scripts/dev.sh start

stop:
	scripts/dev.sh stop

status:
	scripts/dev.sh status

migrate:
	$(ENV) $(BIN)/df-migrate

api:
	$(ENV) $(BIN)/uvicorn df_api.main:app --reload --port 8000

worker:
	$(ENV) $(BIN)/df-worker

web:
	cd apps/web && npm run dev

# Shared config for the SketchUp extension and the worker (port, token, job folder).
bridge-setup:
	$(PY) scripts/bridge_setup.py

# dist/designforge_bridge.rbz → SketchUp: Extensions → Extension Manager → Install Extension
bridge-rbz:
	$(PY) extensions/sketchup-bridge/build_rbz.py

# Stand-in for SketchUp: speaks the bridge protocol so the MCP path can run without SketchUp.
bridge-fake:
	$(ENV) $(BIN)/python extensions/sketchup-bridge/dev/fake_bridge.py

test:
	cd python && ../$(BIN)/pytest -q
	cd apps/api && ../../$(BIN)/pytest -q
