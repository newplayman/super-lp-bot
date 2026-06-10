# WALLET_SIGNER_BROADCASTER_AUDIT — Tiny Canary Preflight

## Goal

Read-only audit of every code path that touches wallet, signer,
or broadcaster. No execution; no signing; no broadcasting; no
printing of secrets. Output: which paths are reachable from
shadow / dryrun / live, what env vars or config keys enable each
path, and the fail-closed behavior when those keys are absent.

## Wallet

### Default `BuildMode == "shadow"` or `BuildMode == "dryrun"`

- The shadow / dryrun binary does NOT import the wallet adapter
  package beyond the type-only interface declaration in
  `internal/ports/wallet.go`. (The shadow binary holds a
  `nil` wallet reference; `runShadowDecisionTraceTable` does not
  call `wallet.ApproveExact`, `wallet.Sign`, or `wallet.Send`.)

### `BuildMode == "live"` only

- `cmd/lpbot/live_execution_live.go::openLiveWallet()` initializes
  the wallet adapter. Source: `internal/adapters/wallet/keystore`.
- The keystore adapter is `//go:build live`. From any other build
  tag, the adapter is not compiled in. A shadow or dryrun binary
  cannot reach `openLiveWallet` because the file is gated.
- `cfg.Wallet.Backend = "keystore"` is the only production
  backend in scope. Other backends (kms, none) are stub
  implementations in their own files.
- `cfg.Wallet.KeystorePath` must point to an existing file on
  disk (`os.Stat` returns true). Empty path → blocker
  `wallet.keystore_path is empty`. Missing file → blocker
  `wallet.keystore_path does not exist on disk`.
- `cfg.Wallet.Passphrase` must be non-empty. Empty → blocker
  `wallet.passphrase is empty`.
- The wallet's `Address().String()` is the only output. It is
  logged via `maskAddress()` (in `live_execution_live.go:57`),
  not via raw `wallet.Address().String()`. No private key is
  printed, logged, or returned. The keystore adapter's `Close()`
  call is deferred at `canary_prepare.go:71`.

### Solana signer

- `cmd/lpbot/solana_*_canary_live.go` reads the signer from
  one of three env vars: `SOLANA_PRIVATE_KEY`,
  `SOLANA_KEYPAIR_JSON`, `SOLANA_KEYPAIR_PATH`. If none is set,
  the function returns `"missing signer env:
  SOLANA_PRIVATE_KEY|SOLANA_KEYPAIR_JSON|SOLANA_KEYPAIR_PATH"`.
- The signer pubkey is then `key.PublicKey()`. It is compared
  against a user-supplied public key. If they mismatch, the
  function returns an error.
- No private key is logged, printed, or persisted to disk.

### Env vars that reach a signer

- `LPBOT_CONFIRM_LIVE` — operator confirmation. Without it, the
  binary refuses to enter live mode (canonical `mode_live.go::Run`
  exits non-zero).
- `SOLANA_PRIVATE_KEY` / `SOLANA_KEYPAIR_JSON` / `SOLANA_KEYPAIR_PATH`
  — Solana signer material.
- `cfg.Wallet.Passphrase` — EVM keystore passphrase.

**Fail-closed**: shadow / dryrun binaries do not reach the
signer code path (not compiled in). The live binary refuses to
start without `LPBOT_CONFIRM_LIVE=YES`. The keystore adapter
refuses to open if the keystore file is missing or the passphrase
is empty. The Solana signer refuses to proceed if no signer env
var is set. **No signer path can be silently entered.**

## Broadcaster

### Default `BuildMode == "shadow"` or `BuildMode == "dryrun"`

- The shadow / dryrun binary does NOT import the live broadcaster
  package. The broadcaster is only wired in `live_execution_live.go`
  which is `-tags=live`.
- Shadow mode logs `simulating transactions without real
  execution.` (`mode_shadow.go:18`). No `tx.Broadcast`,
  `tx.Send`, or `tx.Submit` is reachable from shadow.

### `BuildMode == "live"` only

- `cmd/lpbot/live_execution_live.go::buildLiveBroadcaster()`
  initializes the broadcaster.
- `internal/adapters/broadcast/live` is the broadcaster package.
  It is the only broadcaster wired in live mode.
- `Execution.Backend = "native-rpc"` requires either
  `chains.base.rpc_primary` (in cfg) or `QUICKNODE_API_KEY`
  (in env). Otherwise: blocker
  `execution backend native-rpc requires chains.base.rpc_primary
  or QUICKNODE_API_KEY`.
- `Execution.Backend = "okx-onchain"` requires OKX API key /
  secret / passphrase in cfg. Otherwise: blocker
  `execution backend okx-onchain requires OKX api
  key/secret/passphrase`.
- `BroadcastConfig.Transport` defaults to free public Base RPC;
  it accepts a configured `transport` URL but the live-execution
  layer only constructs it from the canonical public list plus
  QuickNode if a key is set.

### Env vars that reach a broadcaster

- Same as signer: `LPBOT_CONFIRM_LIVE` is the operator gate.
- `QUICKNODE_API_KEY` (optional) — adds private endpoints to the
  broadcaster's transport list.
- `Execution.NPMBaseAddress` (config) — required for native-rpc
  execution backend.

**Fail-closed**: shadow / dryrun binaries do not reach the
broadcaster code path. The live binary refuses to start without
`LPBOT_CONFIRM_LIVE=YES`. Without a configured RPC or QuickNode
key, the broadcaster is not constructed. **No broadcaster path can
be silently entered.**

## Env vars that ENABLE signing / broadcasting

The intersection of:

1. `BuildMode == "live"` (build tag)
2. `LPBOT_CONFIRM_LIVE=YES` (env)
3. `Live.Enabled=true` (config)
4. `Live.WalletAddress` set (config)
5. `Live.AllowedChains` non-empty (config)
6. `Live.AllowedPools` non-empty (config)
7. `Live.MaxOrderUSD` in `(0, 20]` for canary (config + hard cap)
8. `Live.DailyLossLimitUSD > 0` (config)
9. `LiveRisk.MaxTotalExposureUSD > 0` (config)
10. `LiveRisk.MaxPendingExposureUSD > 0` (config)
11. `Wallet.KeystorePath` exists (config + filesystem)
12. `Wallet.Passphrase` non-empty (config)
13. `Execution.Backend` configured (config)
14. `Execution.NPMBaseAddress` non-empty (config)
15. RPC configured (chains.base.rpc_primary OR QUICKNODE_API_KEY)

Any single one of (1)–(15) unsatisfied fails closed at startup
or at the first live action boundary.

## Preflight verdict (this stage)

**No wallet / signer / broadcaster code path is reachable from
shadow or dryrun builds.** This is the build-tag guarantee.
**No live code path can run unless 15 distinct gates are all
satisfied.** The defaults fail every gate.

This stage confirms:

- No signing API touched.
- No broadcast API touched.
- No wallet API touched.
- No private key, mnemonic, seed, or passphrase was read,
  printed, logged, or written to disk.
- No LPBOT_CONFIRM_LIVE was set; no live binary was built with
  the `live` tag and run.

**Therefore: a tiny canary execution plan can be authored with
the confidence that every wallet / signer / broadcaster path is
fail-closed at the gate level, not at the action level.**