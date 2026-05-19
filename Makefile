SHELL := /bin/bash
GO ?= go
BUILD_TAGS_DRYRUN := dryrun
BUILD_TAGS_SHADOW := shadow
BUILD_TAGS_LIVE := live

.PHONY: lint test test-property test-fork test-chaos test-all \
        build-dryrun build-shadow build-live build-all \
        run-dryrun run-shadow run-live \
        backtest tidy clean

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

build-dryrun:
	$(GO) build -tags=$(BUILD_TAGS_DRYRUN) -o bin/lpbot-dryrun ./cmd/lpbot

build-shadow:
	$(GO) build -tags=$(BUILD_TAGS_SHADOW) -o bin/lpbot-shadow ./cmd/lpbot

build-live:
	$(GO) build -tags=$(BUILD_TAGS_LIVE) -o bin/lpbot-live ./cmd/lpbot

build-all: build-dryrun build-shadow build-live backtest

backtest:
	$(GO) build -o bin/lpbot-backtest ./cmd/lpbot-backtest

run-dryrun: build-dryrun
	./bin/lpbot-dryrun --config=configs/config.dryrun.toml

run-shadow: build-shadow
	./bin/lpbot-shadow --config=configs/config.shadow.toml

run-live: build-live
	./bin/lpbot-live --config=configs/config.live.toml

clean:
	rm -rf bin/ data/
