# Audit Module

## Purpose

The audit module provides pool security analysis for rug pulls, honeypots, and fee-on-transfer tokens.

## Scope

- Pool security audits (rug detection, honeypot checks, fee-on-transfer)
- Integration with `<env>.pool.scored` bus events from Scanner
- Produces `<env>.pool.audited` events consumed by Strategy and AuditLog

## Architecture

```
Scanner → [pool.scored] → Audit → [pool.audited] → Strategy
                             ↘ [pool.frozen] → Watchdog
```

## Interface

See `interface.go` for the `Auditor` interface definition.

## Dependencies

- `domain`: Pool, AuditReport, AuditVerdict types
- `ports.Bus`: for event publishing

## Status

- Phase 0: Scaffold stub (defaultAudit panics)