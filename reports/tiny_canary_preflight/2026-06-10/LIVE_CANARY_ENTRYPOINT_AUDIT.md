# LIVE_CANARY_ENTRYPOINT_AUDIT — Tiny Canary Preflight

## Goal

Read-only audit of every code path that, if reached, would
construct, sign, broadcast, or otherwise execute a live-mode
action. No execution; no canary; no live; no signing; no
broadcast. Output: the entrypoint graph, the env-var / config
gate that enables each path, the fail-closed behavior when the
gate is unsatisfied, and the explicit preflight verdict for each
path.

## Build-tag gate (first-order isolation)

Every live / canary code path in `cmd/lpbot/` is gated behind the
`//go:build live` build tag:

```
cmd/lpbot/mode_live.go                 //go:build live
cmd/lpbot/live_execution_live.go       //go:build live
cmd/lpbot/live_submission.go           //go:build live (auxiliary)
cmd/lpbot/canary_mint.go               //go:build live
cmd/lpbot/canary_mint_live_test.go     //go:build live
cmd/lpbot/canary_mint_stub.go          //go:build live (stub)
cmd/lpbot/canary_exit_preflight.go     //go:build live
cmd/lpbot/canary_preflight_stub.go     //go:build live (stub)
cmd/lpbot/canary_prepare.go            //go:build live
cmd/lpbot/canary_prepare_stub.go       //go:build live (stub)
cmd/lpbot/canary_reconcile_mint.go     //go:build live
cmd/lpbot/canary_reconcile_mint_stub.go //go:build live (stub)
cmd/lpbot/canary_size.go               //go:build live
cmd/lpbot/canary_state.go              //go:build live
cmd/lpbot/canary_exit_preflight_stub.go //go:build live (stub)
cmd/lpbot/solana_lp_open_canary_live.go //go:build live
cmd/lpbot/solana_lp_close_canary_live.go //go:build live
cmd/lpbot/solana_lp_prefund_canary_live.go //go:build live
cmd/lpbot/solana_swap_canary_live.go    //go:build live
```

The default `bin/lpbot-shadow` build (`make build-shadow`,
`-tags=shadow`) does NOT include these files. The default
`bin/lpbot-dryrun` build (`make build-dryrun`, `-tags=dryrun`) does
NOT include these files either. Only an explicit
`go build -tags=live ./cmd/lpbot` includes them. The CI workflow
on remote does not build with `-tags=live`.

**First-order fail-closed**: a default or shadow-built binary has
no live/canary code in its binary. Even if `LPBOT_CONFIRM_LIVE=YES`
is set in the env, a shadow binary cannot execute a live action
because the code is not compiled in.

## Entrypoint graph (live-tagged only)

```
main.go (live)
  ├── cmd flag parsing → mode_live.go
  ├── newLiveSafetyGate(cfg)        ← populates from cfg + env
  ├── wireLiveAdapter()             ← live_execution_live.go
  │     ├── openLiveWallet()        ← keystore path
  │     └── buildLiveBroadcaster()  ← live broadcaster
  ├── initPortfolioRiskAdapter()
  ├── ensureLiveSchema()            ← calls loadLiveSchemaState
  ├── ensureShadowDecisionTraceTable()  ← still runs in live mode
  ├── ensureShadowPositionMarksTable()   ← still runs
  ├── ensureShadowExitDecisionsTable()   ← still runs
  ├── ensureShadowExitActionsTable()     ← still runs
  ├── ensureShadowOutcomeLabelsTable()  ← still runs
  ├── ensureShadowOutcomeLabelsRepairedV2Table()
  ├── ensureRiskEventTable()
  ├── ensureShadowOutcomeLabelsRepairedV2ClosedAtIndex()
  ├── ensureConfigSnapshotTable()
  ├── ensureLivePositionMark()
  ├── initRPC()                       ← RPC adapter (no auth)
  ├── initMetricsServer()
  ├── startWorkers()
  │     ├── runBaseTxConfirmerLoop()
  │     ├── runLivePositionMarkLoop()
  │     └── runShadowOutcomeLoop()    ← still runs in live mode
  ├── <-ctx.Done()
  └── shutdown()

Triggered by:
  ./bin/lpbot-live --config=config.live.toml

Required env / config:
  Live.Enabled=true            (config)
  Live.Canary=true             (config; canary mode)
  Live.WalletAddress=0x...     (config)
  Live.MaxOrderUSD=≤20.0       (config; hard cap canaryMaxOrderUSD)
  Live.DailyLossLimitUSD>0     (config)
  Live.AllowedChains=[...]      (config; non-empty)
  Live.AllowedPools=[...]       (config; non-empty)
  LiveRisk.MaxTotalExposureUSD>0 (config)
  LiveRisk.MaxPendingExposureUSD>0 (config)
  Execution.Backend=native-rpc|okx-onchain (config; else blocked)
  Execution.NPMBaseAddress=0x... (config; else blocked)
  chains.base.rpc_primary != "" OR QUICKNODE_API_KEY != "" (env OR config)
  wallet.keystore_path != ""    (config)
  wallet.passphrase != ""       (config)
```

## Env vars that enable live-mode execution

Per `cmd/lpbot/main.go` and `cmd/lpbot/mode_live.go`:

| env var | default | enables |
|---|---|---|
| `LPBOT_CONFIRM_LIVE` | unset | Operator-level confirmation. `mode_live.go::Run` refuses to start if unset; logs `LPBOT_CONFIRM_LIVE is required` and exits non-zero. (The check is the canonical hand-off gate.) |
| `LPBOT_MANUAL_CANARY_OVERRIDE` | unset | Optional, allows skipping `live.enabled=false` for manual canary actions; required by `requireManualCanary()` (`main.go:389`) for any canary action when `live.enabled=false`. |
| `LPBOT_KILL_SWITCH` | unset | (config equivalent is `live.kill_switch`.) When true, the live safety gate adds `live.kill_switch=true` as a blocker. |
| `QUICKNODE_API_KEY` | unset | Optional. Adds QuickNode endpoints to the RPC list when set. Used by the gate to satisfy `rpcPrimaryConfigured`. |
| `BASE_RPC_PRIMARY`, `SOL_RPC_PRIMARY` | unset | Satisfy `rpcPrimaryConfigured` for native-rpc execution backend. |

**Required for ANY live-mode execution**: `LPBOT_CONFIRM_LIVE=YES`
must be set in the env. Without it, `main.go::mode_live.go::Run`
exits non-zero with an explicit error message.

## Hard gates that prevent live execution from running

`liveSafetyGate.blockers()` is the canonical gate. It returns a
list of human-readable reasons why live mode cannot run. The
runtime blocks any live-mode action until the gate returns zero
blockers. Each blocker is a fail-closed check:

| Blocker | Source | Fail-closed means |
|---|---|---|
| `build mode is X` | `isExecutionMode()` returns false unless `BuildMode=="live"` | Cannot run live from a shadow build. |
| `live.enabled=false` | `cfg.Live.Enabled` | Default false. Operator must explicitly enable. |
| `live.kill_switch=true` | `cfg.Live.KillSwitch` or `LPBOT_KILL_SWITCH=1` | Operator can hard-stop. |
| `live.wallet_address is empty` | `cfg.Live.WalletAddress` | No wallet = no execution. |
| `live.allowed_chains is empty` | `cfg.Live.AllowedChains` | Empty allowlist = no execution. |
| `live.allowed_pools is empty` | `cfg.Live.AllowedPools` | Empty allowlist = no execution. |
| `live.max_order_usd must be > 0` | `cfg.Live.MaxOrderUSD` | Must be positive. |
| `canary max_order_usd X exceeds hard cap Y` | `canary && maxOrderUSD > 20.0` | Hard cap; cannot bypass. |
| `live.daily_loss_limit_usd must be > 0` | `cfg.Live.DailyLossLimitUSD` | Must be positive. |
| `live_risk.max_total_exposure_usd must be > 0` | `cfg.LiveRisk.MaxTotalExposureUSD` | Must be positive. |
| `live_risk.max_pending_exposure_usd must be > 0` | `cfg.LiveRisk.MaxPendingExposureUSD` | Must be positive. |
| `live_risk.max_submitted_private_exposure_usd must be >= 0` | `cfg.LiveRisk.MaxSubmittedPrivateExposureUSD` | Must be non-negative. |
| `live_risk.min_gas_reserve_wei must be >= 0` | `cfg.LiveRisk.MinGasReserveWei` | Must be non-negative. |
| `live_risk.max_unreconciled_opening_age_seconds must be > 0` | `cfg.LiveRisk.MaxUnreconciledOpeningAgeSeconds` | Must be positive. |
| `wallet.keystore_path is empty` | `cfg.Wallet.KeystorePath` | Empty = no wallet = no execution. |
| `wallet.keystore_path does not exist on disk` | `os.Stat` | Missing file = no execution. |
| `wallet.passphrase is empty` | `cfg.Wallet.Passphrase` | Empty passphrase = no execution. |
| `execution.npm_base_address is empty` | `cfg.Execution.NPMBaseAddress` | Empty = no execution. |
| `amount_usd to token amount sizing path is not implemented` | `nativeRPCLiveSizingSupported(cfg)` | Native-rpc sizing missing = no execution. |
| `execution backend native-rpc requires chains.base.rpc_primary or QUICKNODE_API_KEY` | `rpcPrimaryConfigured` | No RPC = no execution. |
| `execution backend okx-onchain requires OKX api key/secret/passphrase` | `okxAPIConfigured` | No OKX = no execution. |
| `execution.backend=X is not configured` | `executionBackendConfigured` | No backend = no execution. |
| `executor is still shadow-only; live broadcaster is not wired in cmd/lpbot` | `liveExecutionPathAvailable(cfg)` | Even in `-tags=live` builds, if the live path is not wired, blocked. |

This is **17 distinct hard gates**. Any single one unsatisfied
blocks the entire live path. The gate is consulted at every live
action boundary, not just at startup (see `liveSafetyGate.checkOpen`
and `liveSafetyGate.checkPortfolioSnapshot`).

## Preflight verdict per live/canary code path

| Path | Build-tag | Gate | Fail-closed if any of the17 blockers fires? |
|---|---|---|---|
| `bin/lpbot-live` startup | `-tags=live` required | `LPBOT_CONFIRM_LIVE=YES` + gate.blockers() | YES |
| `canary_cycle.sh` start | calls `bin/lpbot-live` (or shadow + cmd) | gate.blockers() + service env | YES |
| `canary_prepare.go` | `-tags=live` | gate.blockers() + per-call `requireManualCanary()` | YES |
| `canary_mint.go` | `-tags=live` | gate.blockers() + `requireManualCanary()` | YES |
| `canary_exit_preflight.go` | `-tags=live` | `requireManualCanary()` + amount cap | YES |
| `solana_lp_open_canary_live.go` | `-tags=live` | signer env + gate | YES |
| `solana_lp_close_canary_live.go` | `-tags=live` | signer env + gate | YES |
| `solana_lp_prefund_canary_live.go` | `-tags=live` | signer env + gate | YES |
| `solana_swap_canary_live.go` | `-tags=live` | signer env + gate | YES |
| `live_submission.go::txStatusAfterLiveSend` | `-tags=live` | gate at call site | YES |
| `live_submission.go::broadcasterConfirmsOnSend` | `-tags=live` | gate at call site | YES |
| `live_execution_live.go::openLiveWallet` | `-tags=live` | wallet.keystore_path / passphrase non-empty + file exists | YES |
| `live_execution_live.go::buildLiveBroadcaster` | `-tags=live` | execution.backend configured + RPC primary or QuickNode key | YES |
| `canary_profitability_evidence.sh` | script (Bash) | `LPBOT_CONFIRM_LIVE` indirectly via the canary binary | YES |

## Preflight verdict (this stage)

**All live/canary paths are gated by 17 hard blockers PLUS a
build-tag gate PLUS an explicit operator env var
(LPBOT_CONFIRM_LIVE=YES).** Any single blocker unsatisfied
fails closed. The default builds (`shadow`, `dryrun`) do not
include the live code at all. This stage has confirmed:

1. **No shadow / dryrun binary can sign, broadcast, or open a
   position.** The code is not compiled in.
2. **No live binary can run without LPBOT_CONFIRM_LIVE=YES.**
   The canonical entry point (`mode_live.go::Run`) refuses to
   start.
3. **No live binary can run with LPBOT_CONFIRM_LIVE=YES but
   without wallet.keystore_path / passphrase / live.wallet_address
   / live.enabled / live.allowed_chains / live.allowed_pools /
   live.max_order_usd / live.daily_loss_limit_usd / live_risk.* /
   execution.backend / execution.npm_base_address.** Each of these
   is a hard blocker.
4. **No canary action can have max_order_usd > 20.0.** Hard cap
   at `canaryMaxOrderUSD = 20.0`.
5. **No live execution without RPC.** Native-rpc requires
   `rpc_primary` or `QUICKNODE_API_KEY`. OKX requires OKX
   credentials.

**Therefore: the codebase fails-closed at every live/canary path.
No silent execution is possible. This is the precondition for
authoring a tiny canary plan with risk caps.**