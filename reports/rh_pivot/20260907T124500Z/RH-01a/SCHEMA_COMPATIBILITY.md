# RH-01a — /rhj/assets schema compatibility

Read-only, offline. Companion to `scripts/lp_rh_registry_v1_readonly.py`.
No chain data, no network, no wallet. Fixtures are synthetic
(`tests/fixtures/rh/synthetic/`, `data_kind=SYNTHETIC_NOT_CHAIN_DATA`).

## Two observed shapes

Robinhood's `/rhj/assets` `tradingCapabilities` object appears in two forms.
The registry must accept both and fail closed on anything else.

| Field | LEGACY_FIELDS | SESSION_NESTED |
|-------|---------------|----------------|
| market (fractional) | `fractionalTradability` (bool) | `market.{whole,fractional}` (`TRADING_STATUS_*`) |
| extended (fractional) | `extendedHoursFractionalTradability` (bool) | `extended.{whole,fractional}` |
| overnight / all-day | `allDayTradability` (bool) | `overnight.{whole,fractional}` |
| decimals | (absent) | `tokenDecimals` (int) |

Legacy carries only fractional tradability; nested carries whole+fractional
per session. The unified `SessionCapability` keeps one status per session.

## Mapping rules

- **LEGACY_FIELDS**
  - `fractionalTradability` → `market`; `extendedHoursFractionalTradability` →
    `extended`; `allDayTradability` → `overnight`.
  - `true` → `TRADABLE`; `false` → `NOT_TRADABLE`; `null`/`""`/missing/other →
    `UNKNOWN`.
- **SESSION_NESTED**
  - `TRADING_STATUS_TRADABLE` → `TRADABLE`.
  - `TRADING_STATUS_NOT_TRADABLE` **or** `TRADING_STATUS_CLOSING_ONLY` →
    `NOT_TRADABLE` (closing-only is not a new-position permission).
  - any other string / `null` / missing → `UNKNOWN`.
  - `whole` vs `fractional` disagree → take the more conservative
    (`NOT_TRADABLE` > `UNKNOWN` > `TRADABLE`).
- **Both present** → compare derived `(market, extended, overnight)`; equal →
  `SESSION_NESTED` with `raw_flags.both_present=True`; unequal →
  `SCHEMA_SEMANTIC_CONFLICT`.
- **Neither / CONFLICT** → all three sessions `UNKNOWN`.

## CONFLICT definition

`SCHEMA_SEMANTIC_CONFLICT` is set only when legacy and nested keys are both
present **and** their derived per-session statuses differ on at least one
session. It is a data-integrity signal, not a "tradable" signal: the
capability is forced to all-`UNKNOWN`, so `is_new_position_allowed` returns
`False` for every session.

## closing-only handling

`TRADING_STATUS_CLOSING_ONLY` maps to `NOT_TRADABLE` (new positions blocked),
but the original string is preserved verbatim in
`raw_flags.raw_trading_capabilities.<session>.{whole,fractional}` so a later
audit can distinguish "closing-only" from "not-tradable" without re-fetching.

## Known uncovered cases

- **Whole-only tradability**: legacy has no whole/fractional split; the
  registry treats legacy as fractional-only. A legacy asset that is whole-
  tradable but not fractional-tradable is not representable.
- **New enum values**: any `TRADING_STATUS_*` value other than the three
  known ones maps to `UNKNOWN` (fail-closed) but is not individually
  classified.
- **Address field name**: not pinned by the PRD; the registry accepts
  `tokenAddress` / `assetAddress` / `address` (first non-null wins).
- **`verify_identity` chain scope**: the registry is keyed by lower address
  only; `chain_id` is stored but not part of the identity key, so a cross-
  chain asset is rejected only when its address is absent from the registry.
- **`tokenDecimals` type**: non-numeric decimals raise on `int()`; only
  missing → `None` is explicitly specified.
