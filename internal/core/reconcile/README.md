# Reconcile Module

## Responsibility

The reconcile module (M14) is responsible for bootstrap reconciliation - comparing on-chain state with local database state at startup to detect discrepancies before entering live mode.

## Input / Output

- **Subscribes bus topic**: None
- **Publishes bus topic**:
  - `<env>.recon.mismatch` (when count/value discrepancies found)
- **Calls ports**:
  - `Chain` - `ListMyPositions` for on-chain state
  - `PositionRepo` - local open positions from DB
  - `ReconRepo` - append reconciliation results
  - `Bus` - publish mismatch events

## Architecture (spec §4.6)

```
Bootstrap Phase:
  For each chain:
    a. chain.ListMyPositions(walletAddr) → on-chain positions
    b. positionRepo.FindByChainAndStatus(chain, 'open') → DB positions
    c. diff: count match ∧ value deviation ≤ 1% → PASS
    d. Any failure → reconciliation_log + reject live entry
  PASS → unlock broadcaster → normal operation
```

## State

- **DB tables**:
  - `reconciliation_log` (append-only, spec §4.2)
- **In-memory**: Bootstrap lock state, chain adapter references

## Invariants

- Maintains #8: Bootstrap reconciliation failure rejects live entry

## Test Coverage

- Unit: Reconciliation comparison logic
- Property: Invariant #8 enforcement
- Fork: N/A (startup-only module)

## Phase Introduction

Phase 0: Stub scaffold (defaultReconcile panics)
Phase 1: Scanner integration + live reconcile
Phase 2: Enhanced mismatch detection
Phase 3: Real-time reconciliation during operation