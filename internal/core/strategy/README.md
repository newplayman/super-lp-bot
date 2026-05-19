# Strategy Module

## Responsibility

Strategy module (M15) is responsible for:
- Selecting candidate pools from scored/audited pool list
- Deciding position range, fee tier, and rebalance parameters
- Emitting `position.intent` bus events for the Risk gate

## Input / Output

- **Subscribes bus topic**:
  - `<env>.pool.scored` (from Scanner)
  - `<env>.pool.audited` (from Audit)
  - `<env>.pool.frozen` (from Audit / Watchdog)
  - `<env>.position.range_breach` (from PnL, for rebalance evaluation)
  - `<env>.position.closed` (from Execution)
- **Publishes bus topic**:
  - `<env>.position.intent` (to Risk)
- **Calls ports**:
  - `PoolRepo` - query eligible pools
  - `PositionRepo` - check existing positions
  - `RiskGate` - (read-only, for thresholds)

## State

- **DB tables**: None (stateless decision module)
- **In-memory**: Current eligible pool set, position allocation budget

## Invariants

- Maintains #1: Total nominal exposure ≤ configured cap
- Maintains #2: No duplicate active position in same pool
- Emits `position.intent` which triggers Risk gate check

## Test Coverage

- Unit: Range calculation, pool selection logic
- Property: Exposure cap enforcement, no duplicate positions
- Fork: N/A (decision-only module)

## Phase Introduction

Phase 0: Stub scaffold (panic implementations)
Phase 1: Scanner integration + pool selection
Phase 2: Full decision engine + shadow mode
Phase 3: Live execution integration