# Tier C Audit Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Base Tier C LP audit pack that rejects CHECK-style bot-volume traps before any small-capital canary LP is considered.

**Architecture:** Keep candidate discovery read-only, then pass every candidate through a deterministic audit pack. The audit pack produces structured flags, severity, verdict, and an explanation; LLM review may consume the pack later, but hard rejects must be code-driven. Start with the CHECK negative rule as the first fixed rule: high volume/TVL plus mirror-like buy/sell activity, low unique trader breadth, smooth volume, and concentrated holders should downgrade or reject a pool even when estimated fee APR is high.

**Tech Stack:** Go, PostgreSQL, GeckoTerminal/Dex-style pool metadata, existing `scanner.ScoredPool`, existing `cmd/lpbot --base-tierc-discovery`, standard `go test`.

---

## File Structure

- Create: `internal/core/tierc/audit_pack.go`
- Create: `internal/core/tierc/audit_pack_test.go`
- Modify: `cmd/lpbot/base_tierc_discovery.go`
- Optional modify only if needed: `cmd/lpbot/dashboard.go`
- Do not modify live mint, prepare, exit, signer, or broadcaster code in this task.

## Audit Pack Contract

Add a focused package `internal/core/tierc` with these public types:

```go
package tierc

import "github.com/lpbot/lpbot/internal/domain"

type Verdict string

const (
	VerdictReject        Verdict = "reject"
	VerdictWatch         Verdict = "watch"
	VerdictCanaryAllowed Verdict = "canary_allowed"
)

type FlagSeverity string

const (
	SeverityInfo     FlagSeverity = "info"
	SeverityWarn     FlagSeverity = "warn"
	SeverityCritical FlagSeverity = "critical"
)

type MarketQuality struct {
	BuyVolume24hUSD      domain.Decimal
	SellVolume24hUSD     domain.Decimal
	BuyCount24h          int64
	SellCount24h         int64
	Buyers24h            int64
	Sellers24h           int64
	VolumeCV5m           domain.Decimal
	MedianAbsPriceMove5m domain.Decimal
	Top10HolderPct       domain.Decimal
	KnownHoneypot        bool
	BuyTaxPct            domain.Decimal
	SellTaxPct           domain.Decimal
}

type PackInput struct {
	Pool            domain.Pool
	Score           domain.Score
	EstimatedFeeAPR domain.Decimal
	VolumeToTVL     domain.Decimal
	MarketQuality   MarketQuality
}

type Flag struct {
	Code     string
	Severity FlagSeverity
	Message  string
	Evidence map[string]string
}

type Pack struct {
	PoolID          string
	Verdict         Verdict
	RiskScore       int
	Flags           []Flag
	EstimatedFeeAPR domain.Decimal
	VolumeToTVL     domain.Decimal
}

func BuildPack(input PackInput) Pack
```

## Rule Set

Implement these deterministic rules in `BuildPack`:

- `bot_volume_symmetry`: if buy/sell volume symmetry is `>= 0.98` and buy/sell count symmetry is `>= 0.98`, add warn.
- `low_trader_breadth`: if total unique buyers+sellers is positive and trades per unique participant is `>= 50`, add warn.
- `smooth_volume`: if `VolumeCV5m > 0` and `VolumeCV5m <= 0.15`, add warn.
- `high_holder_concentration`: if `Top10HolderPct >= 80%`, add critical.
- `token_tax_or_honeypot`: if honeypot is true or buy/sell tax is above zero, add critical.
- `native_zero_token`: if token0 or token1 is `0x0000000000000000000000000000000000000000`, add critical.
- `thin_tvl`: if TVL is below `25000`, add critical.
- `low_real_volume`: if 24h volume is below `50000`, add warn.
- `high_fee_but_bot_like`: if estimated fee APR is `>= 100%` and at least two bot-volume flags are present, add critical.

Risk score:

```text
critical flag = +40
warn flag = +15
info flag = +5
cap risk_score at 100
```

Verdict:

```text
reject: any critical flag, or risk_score >= 60
watch: risk_score >= 25
canary_allowed: otherwise
```

## CHECK Negative Rule

Add a unit test that models CHECK/USDC Aerodrome data:

```text
pool_id = 0x3c4384f3664b37a3cb5a5cb3452b4b4a3aa1256f
token0 = 0x9126236476EFBA9AD8AB77855C60EB5BF37586EB
token1 = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
tvl = 886992.88
vol24h = 4790372.57
fee_bps = 25
estimated_fee_apr ~= 492.81%
buy_volume = 2394000
sell_volume = 2401000
buy_count = 13898
sell_count = 13874
buyers = 133
sellers = 166
volume_cv_5m = 0.115
median_abs_price_move_5m = 0.00014
top10_holder_pct = 91.05
tax = 0
honeypot = false
```

Expected:

```text
verdict = reject
flags include bot_volume_symmetry
flags include low_trader_breadth
flags include smooth_volume
flags include high_holder_concentration
flags include high_fee_but_bot_like
```

## Task 1: Build Tier C Audit Pack

**Files:**
- Create: `internal/core/tierc/audit_pack.go`
- Create: `internal/core/tierc/audit_pack_test.go`

- [ ] **Step 1: Add failing CHECK negative test**

Create `internal/core/tierc/audit_pack_test.go` with tests for CHECK reject, normal watch, native zero token reject, and clean canary allowed.

Run:

```bash
go test ./internal/core/tierc
```

Expected before implementation:

```text
FAIL
```

- [ ] **Step 2: Implement `BuildPack`**

Create `internal/core/tierc/audit_pack.go` with the public contract and rules above. Keep helper functions private and deterministic. Use decimal arithmetic for ratios.

- [ ] **Step 3: Verify package tests**

Run:

```bash
go test ./internal/core/tierc
```

Expected:

```text
ok github.com/lpbot/lpbot/internal/core/tierc
```

## Task 2: Wire Audit Pack Into Base Discovery

**Files:**
- Modify: `cmd/lpbot/base_tierc_discovery.go`

- [ ] **Step 1: Import `internal/core/tierc`**

Discovery output must call `tierc.BuildPack` for each matched candidate.

- [ ] **Step 2: Add read-only market quality placeholders**

Until holder and per-address swap data is implemented, populate `MarketQuality` only with values available today:

```go
MarketQuality{
	BuyVolume24hUSD: domain.ZeroDecimal(),
	SellVolume24hUSD: domain.ZeroDecimal(),
	BuyCount24h: 0,
	SellCount24h: 0,
	Buyers24h: 0,
	Sellers24h: 0,
	VolumeCV5m: domain.ZeroDecimal(),
	MedianAbsPriceMove5m: domain.ZeroDecimal(),
	Top10HolderPct: domain.ZeroDecimal(),
}
```

Also add heuristic placeholders:

```text
native_zero_token still works from token address
high fee APR and high volume/TVL are visible
CHECK negative only fully triggers in tests until richer market fields are wired
```

- [ ] **Step 3: Include verdict in CLI output**

Change output header to:

```text
rank|verdict|risk_score|flags|pool_id|protocol|fee_bps|score_total|est_fee_apr_pct|vol_tvl_ratio|tvl_usd|vol24h_usd|token0|token1|gecko_url
```

Flags should be semicolon-separated flag codes.

- [ ] **Step 4: Sort by verdict first**

Sort candidates as:

```text
canary_allowed before watch before reject
then higher estimated_fee_apr
then higher volume_to_tvl
```

This prevents rejected high-APR traps from appearing as top recommendations.

- [ ] **Step 5: Verify command compiles**

Run:

```bash
go test ./cmd/lpbot
go build -tags=shadow -o /tmp/lpbot-shadow ./cmd/lpbot
```

---

## Phase 2: Real Market-Quality Integration

**Goal:** Replace placeholder `MarketQuality` with real data where the repository can fetch it today, and introduce explicit provider boundaries for the fields the repository cannot fetch reliably yet.

### Current API Reality

- GeckoTerminal pool API provides:
  - `transactions.h24.{buys,sells,buyers,sellers}`
  - `volume_usd.{m5,h1,h6,h24}`
  - price change windows
- GeckoTerminal OHLCV API provides:
  - candle tuples `[timestamp, open, high, low, close, volume]`
  - current client parsing is stale and must be fixed before `VolumeCV5m` or median move can be trusted
- DexScreener pair API provides:
  - `txns` windows and total volume windows
  - no reliable split buy/sell volume
- DexScreener recent swaps endpoint currently used in the repo is not a valid public endpoint for this pool path and should not be treated as a reliable source for trader concentration
- The repository currently has **no reliable holder concentration provider** and **no reliable per-address swap concentration provider**

### Scope Rules

- Do **not** invent buyer/seller volume split if the upstream API does not provide it
- Do **not** invent trader address concentration if the upstream API does not provide trader addresses
- Do **not** block the feature on holder concentration or trader concentration; instead, define provider interfaces with a safe null/default implementation
- Keep discovery read-only
- Do not touch mint/prepare/exit execution code

## Phase 2 Task 1: Fix GeckoTerminal Client Schema

**Files:**
- Modify: `internal/adapters/datasource/geckoterminal/client.go`
- Optional modify if needed: `internal/adapters/datasource/geckoterminal/adapter.go`

- [ ] Update `GetPoolInfo` response structs to match real GeckoTerminal fields:
  - `attributes.transactions.h24.{buys,sells,buyers,sellers}`
  - `attributes.volume_usd.{m5,h1,h6,h24}`
  - `attributes.price_change_percentage`
  - keep existing fields used elsewhere compatible
- [ ] Update `GetOHLCV` response parsing to match the real schema:
  - `data.attributes.ohlcv_list`
  - each candle tuple is `[timestamp, open, high, low, close, volume]`
- [ ] Preserve rate-limit behavior and fallback behavior

## Phase 2 Task 2: Add Tier C Market-Quality Collector

**Files:**
- Create: `cmd/lpbot/base_tierc_market_quality.go`
- Modify: `cmd/lpbot/base_tierc_discovery.go`

Add a focused collector that can assemble:

```go
type tierCMarketQualityCollector interface {
    Collect(ctx context.Context, pool domain.Pool) (tierc.MarketQuality, error)
}
```

Concrete behavior for now:

- `BuyCount24h`, `SellCount24h`, `Buyers24h`, `Sellers24h`:
  - populate from GeckoTerminal pool info when available
- `VolumeCV5m`, `MedianAbsPriceMove5m`:
  - compute from GeckoTerminal 5m OHLCV over the last 24h
- `BuyVolume24hUSD`, `SellVolume24hUSD`:
  - leave zero unless a real split source is added
- `Top10HolderPct`:
  - leave zero in the default collector
- `KnownHoneypot`, `BuyTaxPct`, `SellTaxPct`:
  - keep default zero/false unless existing metadata source is later added

Collector requirements:

- fail open for non-critical enrichment errors
- return partial quality data if OHLCV succeeds but pool metadata is rate-limited, or vice versa
- avoid duplicate per-pool fetches inside one discovery run

## Phase 2 Task 3: Introduce Provider Boundaries for Missing Data

**Files:**
- Create: `internal/core/tierc/providers.go`
- Modify: `cmd/lpbot/base_tierc_market_quality.go`

Add explicit interfaces for fields we cannot fetch reliably today:

```go
type HolderConcentrationProvider interface {
    Top10HolderPct(ctx context.Context, chain domain.ChainID, token domain.Address) (domain.Decimal, error)
}

type TraderConcentrationProvider interface {
    Concentration(ctx context.Context, chain domain.ChainID, poolID string) (map[string]string, error)
}
```

For this phase:

- ship a `NoopHolderConcentrationProvider`
- ship a `NoopTraderConcentrationProvider`
- do not fabricate evidence
- make the default collector use the no-op providers

This is where later Basescan, Birdeye, Dune, self-indexed swap tables, or LLM-reviewed audit snapshots can plug in without rewriting discovery.

## Phase 2 Task 4: Upgrade Audit Logic for Partial Data

**Files:**
- Modify: `internal/core/tierc/audit_pack.go`
- Modify: `internal/core/tierc/audit_pack_test.go`

Rules must behave correctly when some fields are unknown:

- `bot_volume_symmetry`:
  - keep current volume+count symmetry rule when both split volumes are present
  - add a weaker count-only warning path when only counts are available and count symmetry is extremely high
- `low_trader_breadth`:
  - continue using unique buyers/sellers if available
- `smooth_volume`:
  - continue using 5m volume CV
- add a new warning rule:
  - `price_stasis_high_volume`
  - trigger when 5m median absolute move is extremely low while total volume/TVL is high
  - intended to catch “high volume but barely moving” bot-managed pools
- keep `known_negative_check` as a fixed negative fixture even after richer data wiring

Tests to add:

- Gecko-backed partial data still yields deterministic verdicts
- count-only symmetry can raise a warning without split buy/sell volume
- smooth volume + price stasis + high fee APR can push a pool to `watch` or `reject` depending on other flags

## Phase 2 Task 5: Discovery Output and JSON Enrichment

**Files:**
- Modify: `cmd/lpbot/base_tierc_discovery.go`

Extend output and JSON snapshot with the fields used for audit:

- `buyers_24h`
- `sellers_24h`
- `buy_count_24h`
- `sell_count_24h`
- `volume_cv_5m`
- `median_abs_price_move_5m`

Do not add fields that are not real.

JSON output should expose:

- `verdict`
- `risk_score`
- `flags`
- `market_quality`

so later LLM review and regression replay can use the same pack inputs.

## Phase 2 Verification

Minimum commands after implementation:

```bash
go test ./internal/core/tierc ./cmd/lpbot
go build -tags=shadow -o ./bin/lpbot-shadow ./cmd/lpbot
./bin/lpbot-shadow --config ./configs/config.shadow.toml --base-tierc-discovery --base-tierc-limit 12 --base-tierc-include-rejects --base-tierc-json-out /tmp/base-tierc-audit.json
```

Expected outcomes:

- CHECK remains `reject`
- zero/native token pools remain `reject`
- JSON output contains non-placeholder market-quality fields where Gecko data is available
- no fabricated holder or trader concentration evidence appears in output

Expected:

```text
both commands pass
```

## Task 3: Persist Audit Pack Evidence

**Files:**
- Modify: `cmd/lpbot/base_tierc_discovery.go`

- [ ] **Step 1: Add optional JSON output file flag**

Add flags:

```text
--base-tierc-json-out
--base-tierc-include-rejects
```

Behavior:

```text
empty json path: no file written
non-empty json path: write array of candidates with pack fields
include rejects false: omit rejected candidates from console ranking, but still count them in summary
include rejects true: print all candidates
```

- [ ] **Step 2: Verify JSON output**

Run:

```bash
go build -tags=shadow -o /tmp/lpbot-shadow ./cmd/lpbot
/tmp/lpbot-shadow --config configs/config.shadow.toml --base-tierc-discovery --base-tierc-json-out /tmp/tierc.json
```

Expected:

```text
/tmp/tierc.json exists and contains verdict, risk_score, flags, pool_id, fee_apr, vol_tvl
```

## Task 4: VPS Deployment And Online Check

**Files:**
- Deploy changed Go files to `/opt/lpbot/lp-bot-v3`

- [ ] **Step 1: Build on VPS**

Run on VPS:

```bash
cd /opt/lpbot/lp-bot-v3
GOTOOLCHAIN=auto go test ./internal/core/tierc ./cmd/lpbot
GOTOOLCHAIN=auto go build -tags=shadow -o ./bin/lpbot-shadow ./cmd/lpbot
```

Expected:

```text
tests pass and binary builds
```

- [ ] **Step 2: Run discovery**

Run on VPS:

```bash
cd /opt/lpbot/lp-bot-v3
set -a
. ./.env.postgres
. ./.env.redis
. ./.env.dashboard
. ./.env.chain
set +a
./bin/lpbot-shadow --config ./configs/config.shadow.toml --base-tierc-discovery --base-tierc-limit 12 --base-tierc-include-rejects --base-tierc-json-out /tmp/base-tierc-audit.json
```

Expected:

```text
CLI output includes verdict and risk_score
/tmp/base-tierc-audit.json exists
CHECK-like pools no longer surface as top canary suggestions when their risk pack is reject
```

## Review Checklist

- [ ] `CHECK/USDC` fixture rejects even though estimated fee APR is high.
- [ ] `0x0000000000000000000000000000000000000000` token side rejects.
- [ ] Discovery output no longer ranks raw APR without verdict.
- [ ] No live transaction path is changed.
- [ ] No secrets are written to docs, source, configs, JSON output, or logs.
- [ ] VPS build passes.
- [ ] VPS online discovery command returns a usable audit table.
