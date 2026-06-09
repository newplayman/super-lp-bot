SHELL := /bin/bash
GO ?= go
BUILD_TAGS_DRYRUN := dryrun
BUILD_TAGS_SHADOW := shadow
BUILD_TAGS_LIVE := live
BUILD_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo local)
BUILD_DATE ?= $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GO_LDFLAGS := -X main.BuildCommit=$(BUILD_COMMIT) -X main.BuildDate=$(BUILD_DATE)

.PHONY: lint test test-property test-fork test-chaos test-all test-race \
        audit-consistency canary-profitability-evidence \
        build-dryrun build-shadow build-live build-all build-migrate-postgres \
        run-dryrun run-shadow run-live \
        backtest tidy clean \
        migrate-postgres migrate-postgres-plan migrate-postgres-status \
        check-shadow-env-consistency \
        check-postgres-migrations-sync \
        quality-gate preflight

tidy:
	$(GO) mod tidy

lint:
	golangci-lint run ./...

test:
	$(GO) test ./...

test-property:
	$(GO) test -tags=property ./...

test-fork:
	$(GO) test -tags=fork ./tests/fork/...

test-chaos:
	$(GO) test -tags=chaos ./tests/chaos/...

test-all: test test-property test-fork test-chaos

# Race detector for the two highest-contention adapter packages. Per the
# P0-PG-01 audit (BLK-PG-10), the codebase previously had no -race
# coverage anywhere; this target provides a focused entry point that
# catches the most likely race-prone paths (the postgres adapter now
# writes to real Postgres; the rpc adapter has goroutines for the
# health loop and probe latency). Full-repo race coverage is
# intentionally NOT in this target to keep iteration time low; expand
# to ./... only when the packages below are clean.
test-race:
	$(GO) test -race -count=1 ./internal/adapters/store/postgres ./internal/adapters/rpc

audit-consistency:
	./scripts/audit_workspace_consistency.sh

# Static check: shadow / canary / live deployment artifacts (systemd unit,
# .env*.example templates, runbook, migrate entry point) are consistent.
# Catches the kind of drift the P0-PG-01 audit flagged (BLK-PG-06).
check-shadow-env-consistency:
	./scripts/check_shadow_env_consistency.sh

# Drift check: the Go runner's embed directory
# (internal/adapters/store/postgres/migrator/sql/) must match
# migrations/postgres/ exactly — same filenames, same count, same sha256.
# Catches the kind of dual-source drift the P0-PG-01 audit flagged.
check-postgres-migrations-sync:
	./scripts/check_postgres_migrations_sync.sh

# Pre-merge quality gate. Aggregates the cheap, fast, network-free
# checks that should run on every commit. Intentionally excludes:
#   - test-property (uses internal goroutine stress; can be flaky)
#   - test-fork / test-chaos (need secrets, schedule-only)
#   - migrate-postgres apply (needs a live postgres; that lives in
#     .github/workflows/migration-quality-gate.yml)
# The full chain for end-to-end migration verification is:
#   make check-postgres-migrations-sync    (this Makefile, no DB)
#   .github/workflows/migration-quality-gate.yml  (postgres:16-alpine service)
quality-gate: check-postgres-migrations-sync test

canary-profitability-evidence:
	./scripts/canary_profitability_evidence.sh

build-dryrun:
	$(GO) build -ldflags "$(GO_LDFLAGS)" -tags=$(BUILD_TAGS_DRYRUN) -o bin/lpbot-dryrun ./cmd/lpbot

build-shadow:
	$(GO) build -ldflags "$(GO_LDFLAGS)" -tags=$(BUILD_TAGS_SHADOW) -o bin/lpbot-shadow ./cmd/lpbot

build-live:
	$(GO) build -ldflags "$(GO_LDFLAGS)" -tags=$(BUILD_TAGS_LIVE) -o bin/lpbot-live ./cmd/lpbot

build-all: build-dryrun build-shadow build-live backtest build-migrate-postgres

backtest:
	$(GO) build -ldflags "$(GO_LDFLAGS)" -o bin/lpbot-backtest ./cmd/lpbot-backtest

# Standalone Go-based Postgres migration runner. See
# internal/adapters/store/postgres/migrator/ for the design and
# cmd/lpbot-migrate-postgres/ for the CLI.
build-migrate-postgres:
	$(GO) build -o bin/lpbot-migrate-postgres ./cmd/lpbot-migrate-postgres

# Postgres migration entry points. Use migrate-postgres-plan /
# migrate-postgres-status to inspect; migrate-postgres to apply.
# The Go runner is the canonical entry point; scripts/migrate-postgres.sh
# is retained as a thin legacy alias.
migrate-postgres:
	./bin/lpbot-migrate-postgres apply

migrate-postgres-plan:
	./bin/lpbot-migrate-postgres plan

migrate-postgres-status:
	./bin/lpbot-migrate-postgres status

run-dryrun: build-dryrun
	./bin/lpbot-dryrun --config=configs/config.dryrun.toml

run-shadow: build-shadow
	./bin/lpbot-shadow --config=configs/config.shadow.toml

run-live: build-live
	./bin/lpbot-live --config=configs/config.live.toml

clean:
	rm -rf bin/ data/
