# Execution Module

## Purpose

The execution module orchestrates the full transaction lifecycle from approved position intents to confirmed on-chain transactions. It implements the OrderManager pattern per spec §6.4.

## Scope

- Position opening (approved intent → signed tx → broadcast → confirmed)
- Position closing (exit intent → signed tx → broadcast → confirmed)
- Rebalance execution (approved rebalance intent → execution)
- Transaction state machine management
- Nonce management and RBF for stuck transactions
- Approve/revoke management for token approvals

## Architecture

```
intent → Risk.Admit → Simulator → TxBuilder → Approve预备 → Signer → MEV Submitter → Confirmer → 状态机
                ↑                                                                                  ↓
            position.approved ─────────────────────────────────────> position.opened/closed
```

### Components

| Component | Responsibility |
|---|---|
| TxBuilder | Constructs unsigned txs with MinOut + Deadline (zero-value panic, invariant #4) |
| Signer | Delegates to Wallet port (no private key state) |
| Submitter | MEV adapter (compile-time absent in dryrun/shadow) |
| Confirmer | Block subscription, confirmation wait, reorg monitoring |

## Bus Integration

### Subscriptions
- `<env>.position.approved`: Trigger execution of approved positions
- `<env>.position.exit_intent`: Trigger exit execution
- `<env>.position.rebalance_approved`: Trigger rebalance execution

### Publications
- `<env>.position.opened`: Emitted after successful open confirmation
- `<env>.position.closed`: Emitted after successful close confirmation
- `<env>.tx.broadcast`: Emitted when transaction is broadcast
- `<env>.tx.confirmed`: Emitted when transaction is confirmed
- `<env>.tx.failed`: Emitted when transaction fails
- `<env>.tx.reorged`: Emitted when transaction is affected by reorg

## Ports Used

- `ports.Chain`: Block subscription, gas estimation
- `ports.EVMChain` / `ports.SolanaChain`: Nonce management
- `ports.Broadcaster`: Transaction broadcast
- `ports.MEVSubmitter`: MEV-protected submission
- `ports.Wallet`: Transaction signing
- `ports.Bus`: Event publication/subscription

## State

- In-memory: NonceManager state, pending tx tracking
- DB: `tx_log` table for transaction state machine

## Invariants

- Invariant #3: dryrun broadcast count == 0
- Invariant #4: TxBuilder requires non-zero MinOut and Deadline
- Invariant #9: ApproveExact only exact amounts, no ApproveMax
- Invariant #10: Position exit must revoke token approvals

## Testing

- Unit: OrderManager state machine transitions
- Property: Invariant #4 (zero-value panic), nonce monotonicity
- Fork: Full open/close cycle on Anvil/Solana devnet

## Phase

- Phase 0: Scaffold stub with panic implementations
- Phase 2: Shadow execution (no real broadcast)
- Phase 3: Live execution with real wallet and broadcast