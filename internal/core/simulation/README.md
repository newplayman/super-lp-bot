# Simulation Module

## Responsibility
Provides the core business logic layer for transaction simulation workflows.
Wraps the `ports.Simulator` interface with business rules for honeypot detection,
slippage validation, and gas estimation before transactions are admitted by the Risk gate.

## Input / Output
- **Subscribes bus topics**: `position.intent`, `position.exit_intent`
- **Publishes bus topics**: `simulation.submitted`, `simulation.result`, `simulation.failed`
- **Calls ports**: `Simulator`, `Pool`, `Store`

## State
- **In-memory**: Simulation request queue (short-lived)
- **DB tables**: `simulation_results` (append-only audit log)

## Invariants
- Maintains invariant: Any add/remove/rebalance/exit tx must first pass simulation (spec §6.3)
- Honeypot detection: Transactions that revert or return unexpected amounts are flagged

## Testing Coverage
- Unit: Simulation request/result types, panic stubs
- Fork: Full simulation flow against Anvil/Solana RPC (Phase 1+)

## Phase Introduction
Phase 0: Scaffold stub with panic implementations
Phase 1: Basic simulation integration with scanner/audit
Phase 2: Full SimulateSequence for multi-step workflows