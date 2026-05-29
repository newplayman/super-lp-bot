# REPAIRED V2 SCHEMA CHECK

- workspace: `/opt/lpbot/lp-bot-v3-origin-check`
- schema_source: existing VPS Postgres + clean remote research scripts
- migration_applied_now: no
- reason: `shadow_outcome_labels_repaired_v2` already exists

## Required Tables

- `shadow_outcome_labels_repaired_v2`: present
- `pool_token_metadata`: present
- `price_snapshots`: present
- `shadow_outcome_labels`: present
- `shadow_decision_trace`: present
- `shadow_position_marks`: present

## Goose Status

- goose binary: missing
- fallback: queried `goose_db_version`
- max_applied_version: `10`
- interpreted_status: base VPS migrations applied through the currently recorded version table

## Decision

- no live schema changes performed
- no table drops performed
- no migration needed before repaired_v2 report run
