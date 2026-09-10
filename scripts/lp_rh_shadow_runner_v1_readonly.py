#!/usr/bin/env python3
"""RH-04b: single-CORE-pool Shadow runner (orchestration only, read-only).

Wires the six RH layers into one replayable, offline-testable Shadow closed
loop.  Calls existing modules; adds no economic logic.  Live store opened
read-only; all Shadow writes go to a scratch store.  No wallet, no broadcast.
"""
import argparse
import json
import math
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
from scripts.lp_rh_terminal_gate_v1_readonly import (
    CONJUNCT_ORDER,
    evaluate_terminal_gate,
)
from scripts.lp_rh_bucket_ledger_v1_readonly import (
    POLICY_ID,
    bucket_active_cap,
    capital_policy_conflict,
    try_reserve,
)
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID
from scripts.lp_rh_market_session_v1_readonly import (
    allows_new_position,
    classify_session,
    evaluate_health,
)
from scripts.lp_rh_exit_depth_v1_readonly import exit_depth_for_size
from scripts.lp_rh_pnl_v1_readonly import compute_nav, hodl_benchmark, net_pnl
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store
from scripts.lp_rh_v3_inventory_v1_readonly import (
    inventory_for_position,
    position_value_at,
)

# Uniswap V3 fee-growth scaling: fees = L * delta(feeGrowthGlobal) / 2**128.
FEE_GROWTH_SCALE = Decimal(2) ** 128
DEFAULT_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
DEFAULT_DB = "reports/lp_rh/scanner.db"
# Virtual two-leg HODL lot (D04: not 50/50); fixed at first step, never reset (T41).
VIRTUAL_INITIAL_TOKEN0_RAW = Decimal("1000000000000000000")
VIRTUAL_INITIAL_TOKEN1_RAW = Decimal("1000000")
DEFAULT_DEC0, DEFAULT_DEC1 = 18, 6
DEFAULT_QUOTE_USD_PER_TOKEN1 = Decimal("1")


@dataclass
class ShadowStep:
    step_index: int
    sample_time: Optional[str]
    price: Optional[Decimal]
    terminal_eligible: bool
    primary_status: str
    dominant_blocker: Optional[str]
    nav: Optional[Decimal]
    net_pnl: Optional[Decimal]
    hodl_value: Optional[Decimal]
    reservation_granted: bool
    simulated_policy_only: bool = True
    conjunct_reasons: tuple = ()
    nav_reason: Optional[str] = None


def _candidate_key(sample: Mapping[str, Any], step_index: int) -> str:
    """Per-step unique candidate key so decision_id (PK) never collides."""
    base = (sample.get("candidate_key") or sample.get("pool_key")
            or sample.get("asset_address") or "pool")
    st = sample.get("sample_time")
    return f"{base}@{st}" if st else f"{base}#{step_index}"


def _terminal_record(sample, gated, step_index, *, pool_meta=None,
                    capital_usd=None, position_usd=None, now=None,
                    conjunct_reasons=None) -> dict:
    """Merge the gated record with the nine non-netcover conjuncts.

    The conjuncts are computed from the modules that own them.  A sample may
    still override any of them explicitly, which is the injection channel the
    tests use; production samples carry none of these keys.
    """
    rec = dict(gated)
    if capital_usd is not None and position_usd is not None and now is not None:
        bits, reasons = compute_conjuncts(
            sample, gated, pool_meta=pool_meta, capital_usd=capital_usd,
            position_usd=position_usd, now=now)
        rec.update(bits)
        if conjunct_reasons is not None:
            conjunct_reasons.extend(reasons)
    for key in CONJUNCT_ORDER:
        if key != "netcover_pass" and key in sample:
            rec[key] = bool(sample[key])
    if "capital_policy_conflict" in sample:
        rec["capital_policy_conflict"] = sample["capital_policy_conflict"]
    rec["candidate_key"] = _candidate_key(sample, step_index)
    return rec


# Freshness ceiling for the reference quote, in seconds.  Measured live at
# 7-20s across all six symbols on 2026-09-08, so 120s is generous but still
# catches a genuinely dead feed.
REFERENCE_MAX_AGE_SECS = 120.0

# Legacy 100U policy floor (PRD D02).  Reported against, never rewritten here.
LEGACY_MIN_POSITION_USD = Decimal("50")


# Evidence keys assemble_rh_clmm_inputs needs that a market-state sample does
# not carry.  They describe the pool, so they ride in with pool_meta rather than
# being invented per sample.
_POOL_EVIDENCE_KEYS = (
    "attestation_status", "protocol", "sqrt_price_x96", "fee", "dec0", "dec1",
    "liquidity_raw", "fee_apr_pct", "sigma_daily", "gas_usd_estimate",
    "range_pct", "tvl_usd", "active_liquidity_notional_usd",
)


# RH-02bq: the eight cost/risk components that sum to the NetCover model's
# expected_risk_cost.  Persisted verbatim (as JSON) so the full-cost breakdown
# is auditable, not just the NetCover ratio.
_COST_COMPONENT_KEYS = (
    "il_ev_usd", "lvr_ev_usd", "entry_cost_usd", "exit_cost_usd",
    "gas_usd", "slippage_usd", "reward_conversion_cost_usd",
    "exit_latency_loss_usd",
)


def _economic_str(value):
    """Store an economic value as a fixed-point decimal string; None stays None.

    The store's money-column guard rejects raw floats and scientific-notation
    strings (str(1.6e-08) == '1.6e-08' fails the decimal regex), so round-trip
    through Decimal for a plain decimal string.  Missing values stay None, never
    0 or '' (fail-close: a missing economic number is not a zero).
    """
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def _evidence_for(sample, pool_meta):
    """Sample plus the pool evidence, without mutating either.

    Only keys the sample does not already define are taken from pool_meta, so a
    sample can always override.  Missing keys stay missing: the assembler fails
    closed on them rather than being handed a default.
    """
    evidence = dict(sample)
    if not pool_meta:
        return evidence
    for key in _POOL_EVIDENCE_KEYS:
        if evidence.get(key) is None and pool_meta.get(key) is not None:
            evidence[key] = pool_meta[key]
    return evidence


def _as_datetime(value):
    """Accept the ISO string the runner passes around, or a datetime.

    ``now_fn()`` yields a string because the gate and the ledger both take one;
    ``classify_session`` and ``evaluate_health`` need a real datetime.  Returns
    None when the value cannot be parsed, so callers fail closed rather than
    raising mid-episode.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def validate_quote_evidence(
    raw_quote: Any,
    sample_time: Any = None,
    *,
    allow_bare_quote: bool = False,
) -> tuple[Optional[Decimal], Optional[str]]:
    """Validate quote evidence against provenance and replay freshness rules.

    Returns (quote_decimal, error_reason).
    When valid, returns (quote_decimal, None).
    When invalid, returns (None, reason) where reason is one of:
      - QUOTE_EVIDENCE_MISSING
      - QUOTE_EVIDENCE_UNPROVENANCED
      - QUOTE_EVIDENCE_INVALID_VALUE
      - QUOTE_EVIDENCE_SOURCE_EMPTY
      - QUOTE_EVIDENCE_OBSERVED_AT_UNPARSEABLE
      - QUOTE_EVIDENCE_INVALID_TTL
      - QUOTE_EVIDENCE_EXPIRED
    """
    if raw_quote is None:
        return None, "QUOTE_EVIDENCE_MISSING"

    if not isinstance(raw_quote, dict):
        if not allow_bare_quote:
            return None, "QUOTE_EVIDENCE_UNPROVENANCED"
        try:
            val = Decimal(str(raw_quote))
            if not val.is_finite() or val <= 0:
                return None, "QUOTE_EVIDENCE_INVALID_VALUE"
            return val, None
        except (TypeError, ValueError, InvalidOperation):
            return None, "QUOTE_EVIDENCE_INVALID_VALUE"

    if "value" not in raw_quote or raw_quote["value"] is None:
        return None, "QUOTE_EVIDENCE_MISSING"

    try:
        val = Decimal(str(raw_quote["value"]))
        if not val.is_finite() or val <= 0:
            return None, "QUOTE_EVIDENCE_INVALID_VALUE"
    except (TypeError, ValueError, InvalidOperation):
        return None, "QUOTE_EVIDENCE_INVALID_VALUE"

    source = raw_quote.get("source")
    if source is None or not str(source).strip():
        return None, "QUOTE_EVIDENCE_SOURCE_EMPTY"

    observed_raw = raw_quote.get("observed_at")
    if observed_raw is None:
        return None, "QUOTE_EVIDENCE_OBSERVED_AT_UNPARSEABLE"
    observed_dt = _as_datetime(observed_raw)
    if observed_dt is None:
        return None, "QUOTE_EVIDENCE_OBSERVED_AT_UNPARSEABLE"

    ttl_raw = raw_quote.get("ttl_secs")
    if ttl_raw is None:
        return None, "QUOTE_EVIDENCE_INVALID_TTL"
    try:
        ttl = float(ttl_raw)
        if not math.isfinite(ttl) or ttl <= 0:
            return None, "QUOTE_EVIDENCE_INVALID_TTL"
    except (TypeError, ValueError):
        return None, "QUOTE_EVIDENCE_INVALID_TTL"

    if sample_time is None:
        return None, "QUOTE_EVIDENCE_EXPIRED"
    sample_dt = _as_datetime(sample_time)
    if sample_dt is None:
        return None, "QUOTE_EVIDENCE_EXPIRED"

    age_secs = (sample_dt - observed_dt).total_seconds()
    if age_secs > ttl:
        return None, "QUOTE_EVIDENCE_EXPIRED"

    return val, None


def parse_health_flags(raw_flags) -> tuple[dict[str, bool], list[str]]:
    """Parse health_flags_json (or sequence) and map to risk booleans.

    Known flags:
      - "CHAIN_DEGRADED" -> chain_degraded=True
      - "HALT" -> halt=True
      - "CORP_ACTION" / "CORP_ACTION_PENDING" -> corp_action_pending=True
      - "SOURCE_DISAGREEMENT" / "SOURCES_DISAGREE" -> sources_disagree=True
      - "CLOCK_SKEW" -> collector internal timing flag (no separate boolean)

    Returns:
      (booleans_dict, errors_list)
      If raw_flags is None, empty string, or empty sequence, all booleans are False and errors are empty.
      If JSON decoding fails, or unknown flags are present, errors will name the failure/flag.
    """
    booleans = {
        "chain_degraded": False,
        "halt": False,
        "corp_action_pending": False,
        "sources_disagree": False,
    }
    errors: list[str] = []

    if raw_flags is None:
        return booleans, errors

    if isinstance(raw_flags, str):
        trimmed = raw_flags.strip()
        if not trimmed:
            return booleans, errors
        try:
            parsed = json.loads(trimmed)
        except Exception as exc:  # noqa: BLE001
            return booleans, [f"HEALTH_FLAGS_JSON_INVALID: {exc}"]
    elif isinstance(raw_flags, (list, tuple, set, frozenset)):
        parsed = raw_flags
    else:
        return booleans, [f"HEALTH_FLAGS_JSON_INVALID: unexpected type {type(raw_flags).__name__}"]

    if not isinstance(parsed, (list, tuple, set, frozenset)):
        return booleans, [f"HEALTH_FLAGS_JSON_INVALID: expected list, got {type(parsed).__name__}"]

    for item in parsed:
        flag = str(item).strip()
        if not flag:
            continue
        if flag == "CHAIN_DEGRADED":
            booleans["chain_degraded"] = True
        elif flag == "HALT":
            booleans["halt"] = True
        elif flag in ("CORP_ACTION", "CORP_ACTION_PENDING"):
            booleans["corp_action_pending"] = True
        elif flag in ("SOURCE_DISAGREEMENT", "SOURCES_DISAGREE"):
            booleans["sources_disagree"] = True
        elif flag in ("CLOCK_SKEW", "ORACLE_PAUSED", "ORACLE_UNAVAILABLE", "ORACLE_STALE", "API_STALE"):
            # Known flags from market session / collector that are either handled elsewhere
            # or purely informational; valid flags that do not raise unknown flag errors.
            pass
        else:
            errors.append(f"HEALTH_FLAGS_UNKNOWN: {flag}")

    return booleans, errors


def compute_conjuncts(sample, gated, *, pool_meta=None, capital_usd,
                      position_usd, now):
    """Compute the nine non-netcover conjuncts from the modules that own them.

    Returns ``(bits, reasons)``.  Every conjunct that cannot be computed is
    False with a named reason: nothing defaults to True to make the loop run.
    ``netcover_pass`` is not produced here -- the gate computes it itself.
    """
    bits: dict = {}
    reasons: list = []

    def fail(name, why):
        bits[name] = False
        reasons.append(f"{name}: {why}")

    # identity_verified -- chain identity gate (PRD 7.1, T01).
    chain_id = sample.get("chain_id")
    if chain_id is None:
        fail("identity_verified", "chain_id missing from sample")
    elif int(chain_id) != RH_CHAIN_ID:
        fail("identity_verified", f"chain_id {chain_id} != {RH_CHAIN_ID}")
    else:
        bits["identity_verified"] = True

    # protocol_capabilities_sufficient -- attested V3 pool, same block.
    if not pool_meta:
        fail("protocol_capabilities_sufficient", "pool_meta not supplied")
    elif pool_meta.get("attestation_status") != "ATTESTED_SAME_BLOCK":
        fail("protocol_capabilities_sufficient",
             f"attestation {pool_meta.get('attestation_status')!r}")
    elif pool_meta.get("protocol") != "v3":
        fail("protocol_capabilities_sufficient",
             f"protocol {pool_meta.get('protocol')!r} unsupported")
    else:
        bits["protocol_capabilities_sufficient"] = True

    # data_complete_and_fresh -- price present, quote young, payload identified.
    age = sample.get("reference_age_secs")
    if sample.get("reference_mid") is None:
        fail("data_complete_and_fresh", "reference_mid is None")
    elif age is None:
        fail("data_complete_and_fresh", "reference_age_secs unknown")
    elif float(age) > REFERENCE_MAX_AGE_SECS:
        fail("data_complete_and_fresh",
             f"reference {float(age):.0f}s old > {REFERENCE_MAX_AGE_SECS:.0f}s")
    elif not sample.get("source_payload_hash"):
        fail("data_complete_and_fresh", "source_payload_hash missing")
    else:
        bits["data_complete_and_fresh"] = True

    # market_and_chain_risk_pass -- session plus health, via the owning module.
    # Resolve the clock first: evaluate_health needs a real datetime too, and
    # handing it None raises rather than failing closed.
    now_dt = _as_datetime(now)
    if now_dt is None:
        fail("market_and_chain_risk_pass", f"unparseable timestamp {now!r}")
        return _finish_conjuncts(bits, reasons, gated, pool_meta,
                                 capital_usd, position_usd, fail)

    # RH-02ao: Health flags parsing & fail-closed on unknown/invalid flags.
    # Check if flags were already parsed into sample or if health_flags_json is present.
    health_errors = sample.get("health_flags_errors")
    if health_errors is None:
        # Fall back to parsing health_flags_json if booleans not pre-populated.
        raw_flags = sample.get("health_flags_json")
        flags_bools, health_errors = parse_health_flags(raw_flags)
        flag_chain_degraded = True if (flags_bools["chain_degraded"] or sample.get("chain_degraded") is True) else False
        flag_halt = True if (flags_bools["halt"] or sample.get("halt") is True) else False
        flag_corp_action = True if (flags_bools["corp_action_pending"] or sample.get("corp_action_pending") is True) else False
        flag_sources_disagree = True if (flags_bools["sources_disagree"] or sample.get("sources_disagree") is True) else False
    else:
        flag_chain_degraded = True if sample.get("chain_degraded") is True else False
        flag_halt = True if sample.get("halt") is True else False
        flag_corp_action = True if sample.get("corp_action_pending") is True else False
        flag_sources_disagree = True if sample.get("sources_disagree") is True else False

    if health_errors:
        for err in health_errors:
            fail("market_and_chain_risk_pass", err)
        return _finish_conjuncts(bits, reasons, gated, pool_meta,
                                 capital_usd, position_usd, fail)

    # CORE bucket: the on-chain pool price has no independent oracle, so the
    # block timestamp (source_event_time) IS the price's generation time and
    # serves as both oracle_updated_at and api_generated_at.  STOCK buckets
    # must instead go through resolve_freshness (RH-02L); never reuse this.
    flags = evaluate_health(
        oracle_paused=True if (sample.get("oracle_paused") is True or sample.get("oracle_paused") == 1) else False,
        oracle_updated_at=sample.get("source_event_time"),
        api_generated_at=sample.get("source_event_time"),
        now=now_dt,
        halt=flag_halt,
        corp_action_pending=flag_corp_action,
        sources_disagree=flag_sources_disagree,
        chain_degraded=flag_chain_degraded,
        oracle_heartbeat_secs=sample.get("oracle_heartbeat_secs") or 3600,
        api_stale_secs=age,
    )
    session, _ = classify_session(now_dt, calendar=None)
    if allows_new_position(session, flags):
        bits["market_and_chain_risk_pass"] = True
    else:
        fail("market_and_chain_risk_pass", f"session={session} flags={flags}")

    return _finish_conjuncts(bits, reasons, gated, pool_meta,
                             capital_usd, position_usd, fail)


def _finish_conjuncts(bits, reasons, gated, pool_meta, capital_usd,
                      position_usd, fail):
    """The five conjuncts that do not depend on the clock, plus the roll-up."""
    # profile_policy_pass -- the bucket's active cap must hold the position.
    try:
        cap = bucket_active_cap(capital_usd, "CORE")
    except Exception as exc:                       # noqa: BLE001
        cap = None
        fail("profile_policy_pass", f"bucket_active_cap raised {type(exc).__name__}")
    if cap is not None:
        if Decimal(str(cap)) >= Decimal(str(position_usd)):
            bits["profile_policy_pass"] = True
        else:
            fail("profile_policy_pass",
                 f"CORE active cap {cap} < position {position_usd}")

    # capital_policy_pass -- D02.  Reported, never auto-adjusted, never unlocked.
    conflict = capital_policy_conflict(capital_usd, legacy_min_position=LEGACY_MIN_POSITION_USD)
    if conflict and conflict.get("conflict"):
        fail("capital_policy_pass",
             f"{conflict.get('code')} core_cap={conflict.get('core_cap')} "
             f"legacy_min={conflict.get('legacy_min')}")
    else:
        bits["capital_policy_pass"] = True

    # absolute_profit_pass -- fee EV must clear the horizon-invariant costs.
    fee_ev = gated.get("fee_ev_usd")
    entry, exit_, gas = (gated.get("entry_cost_usd"), gated.get("exit_cost_usd"),
                         gated.get("gas_usd"))
    if fee_ev is None or entry is None or exit_ is None or gas is None:
        fail("absolute_profit_pass", "fee EV or a cost leg is unavailable")
    else:
        net = (Decimal(str(fee_ev)) - Decimal(str(entry))
               - Decimal(str(exit_)) - Decimal(str(gas)))
        if net > 0:
            bits["absolute_profit_pass"] = True
        else:
            fail("absolute_profit_pass", f"net EV {net} <= 0")

    # position_and_exit_depth_pass -- the pool must absorb an exit at this size.
    if not pool_meta or not pool_meta.get("tick_data"):
        fail("position_and_exit_depth_pass", "pool_meta lacks tick_data")
    else:
        depth = exit_depth_for_size(
            position_value_usd=Decimal(str(position_usd)),
            max_impact_bps=Decimal(str(pool_meta.get("max_impact_bps", 50))),
            **{k: v for k, v in pool_meta.items()
               if k not in ("attestation_status", "protocol", "max_impact_bps")})
        if depth.get("sufficient"):
            bits["position_and_exit_depth_pass"] = True
        else:
            fail("position_and_exit_depth_pass", str(depth.get("reason")))

    # legacy_required_conjunction -- the roll-up of the other eight.  Listed
    # first in CONJUNCT_ORDER, so it must be computed last.
    others = [k for k in CONJUNCT_ORDER
              if k not in ("legacy_required_conjunction", "netcover_pass")]
    missing = [k for k in others if not bits.get(k)]
    if missing:
        fail("legacy_required_conjunction", f"depends on {missing}")
    else:
        bits["legacy_required_conjunction"] = True

    return bits, reasons


def run_episode(conn, *, strategy_episode, samples, position_usd, horizon_hours,
                capital_usd, target_mode, now_fn, pool_meta=None,
                allow_bare_quote=False):
    """Replay one Shadow episode over `samples`, writing gate decisions and position marks to `conn`."""
    steps: list[ShadowStep] = []
    position_open = False
    prev_nav: Optional[Decimal] = None
    prev_fg0: Optional[Decimal] = None
    prev_fg1: Optional[Decimal] = None
    accrued = Decimal(0)
    open_resolved = False
    open_valid = False
    open_fail_reason: Optional[str] = None
    entry_price: Optional[Decimal] = None
    range_pct_val: Optional[Decimal] = None
    dec0_val: int = DEFAULT_DEC0
    dec1_val: int = DEFAULT_DEC1
    quote_val: Optional[Decimal] = None
    amount0_human: Optional[Decimal] = None
    amount1_human: Optional[Decimal] = None
    liquidity_human: Optional[Decimal] = None
    l_pos: Optional[Decimal] = None
    active_quote_evidence = None

    for i, sample in enumerate(samples):
        record = assemble_rh_clmm_inputs(_evidence_for(sample, pool_meta),
                                         position_usd=position_usd,
                                         horizon_hours=horizon_hours)
        gated = apply_netcover_gate([record])[0]
        step_reasons: list = []
        # RH-02ab: judge at the sample's own time, not the wall clock.  A replay
        # decision is "what would we have done at that moment?", so the gate's
        # clock is the sample's sample_time.  When sample_time is missing or
        # unparseable there is no replay moment to judge at: fall back to the
        # wall clock for the timestamp, but the step must fail rather than pass
        # (a decision without a replay moment is not a decision).
        sample_time = sample.get("sample_time")
        decision_now = sample_time if _as_datetime(sample_time) is not None else now_fn()
        decision = evaluate_terminal_gate(
            _terminal_record(sample, gated, i, pool_meta=pool_meta,
                             capital_usd=capital_usd, position_usd=position_usd,
                             now=decision_now, conjunct_reasons=step_reasons),
            target_mode=target_mode, now=decision_now)
        eligible = bool(decision.terminal_eligible)
        simulated = bool(decision.simulated_policy_only)

        granted = False
        if eligible and not position_open:
            res = try_reserve(conn, intent_id=f"rh-shadow-{strategy_episode}-{i}",
                              bucket="CORE", amount_usd=position_usd,
                              capital_usd=capital_usd, policy_version=POLICY_ID,
                              now=decision_now)
            granted = bool(res.get("granted"))
            if granted:
                position_open = True

        raw_price = sample.get("reference_mid")
        price = Decimal(str(raw_price)) if raw_price is not None else None

        raw_quote = sample.get("quote_usd_per_token1")
        if raw_quote is None and pool_meta is not None:
            raw_quote = pool_meta.get("quote_usd_per_token1")
        if raw_quote is not None:
            active_quote_evidence = raw_quote

        step_quote_val, quote_reason = validate_quote_evidence(
            active_quote_evidence,
            sample_time=sample_time,
            allow_bare_quote=allow_bare_quote,
        )

        # RH-02al / RH-02bd / RH-02bg: On the first step with a valid reference_mid (the open step),
        # resolve and cache the position inventory and liquidity. Fail-closed:
        # if pool_meta lacks range_pct, or entry_price missing, or quote missing/expired/unprovenanced,
        # or dec0/dec1 missing, open_valid stays False and nav/hodl remain None for the episode.
        # No silent defaults for quote (PRD:651 forbids forcing $1) or decimals.
        if not open_resolved and price is not None and price > 0:
            open_resolved = True
            if pool_meta is not None and "range_pct" in pool_meta:
                try:
                    r_pct = Decimal(str(pool_meta["range_pct"]))

                    # Decimals must be explicitly present in pool_meta or sample
                    d0_raw = pool_meta.get("dec0", pool_meta.get("token0_decimals", sample.get("dec0")))
                    d1_raw = pool_meta.get("dec1", pool_meta.get("token1_decimals", sample.get("dec1")))
                    if d0_raw is None or d1_raw is None:
                        open_fail_reason = "DECIMALS_MISSING"
                        raise ValueError("dec0/dec1 missing")
                    d0 = int(d0_raw)
                    d1 = int(d1_raw)

                    if step_quote_val is None:
                        open_fail_reason = quote_reason
                        raise ValueError(f"quote invalid: {quote_reason}")

                    p_usd = Decimal(str(position_usd))
                    if r_pct > 0 and r_pct < 100 and step_quote_val > 0 and d0 >= 0 and d1 >= 0 and p_usd > 0:
                        inv = inventory_for_position(
                            position_usd=p_usd,
                            entry_price=price,
                            range_pct=r_pct,
                            dec0=d0,
                            dec1=d1,
                            quote_usd_per_token1=step_quote_val,
                        )
                        scale = (Decimal(10) ** d0 * Decimal(10) ** d1).sqrt()
                        entry_price = price
                        range_pct_val = r_pct
                        dec0_val = d0
                        dec1_val = d1
                        quote_val = step_quote_val
                        amount0_human = inv.amount0_human
                        amount1_human = inv.amount1_human
                        liquidity_human = inv.liquidity_raw / scale
                        l_pos = inv.liquidity_raw
                        open_valid = True
                    else:
                        open_fail_reason = open_fail_reason or "RANGE_OR_INPUTS_INVALID"
                except (TypeError, ValueError, InvalidOperation):
                    open_valid = False
            else:
                open_valid = False
                open_fail_reason = "RANGE_PCT_MISSING"

        fg0, fg1 = sample.get("fee_growth_global_0"), sample.get("fee_growth_global_1")
        nav: Optional[Decimal] = None
        nav_reason: Optional[str] = None
        if not open_valid:
            nav = None
            nav_reason = open_fail_reason or quote_reason or "OPEN_INVALID"
        elif price is None:
            nav = None
            nav_reason = "PRICE_MISSING"
        elif step_quote_val is None:
            nav = None
            nav_reason = quote_reason
        elif fg0 is None or fg1 is None:
            nav = None
            nav_reason = "FEE_GROWTH_MISSING"
        else:
            try:
                cur0, cur1 = Decimal(str(fg0)), Decimal(str(fg1))
                if prev_fg0 is not None and prev_fg1 is not None:
                    d0 = cur0 - prev_fg0
                    d1 = cur1 - prev_fg1
                    tok0 = (l_pos * d0 / FEE_GROWTH_SCALE / (Decimal(10) ** dec0_val))
                    tok1 = (l_pos * d1 / FEE_GROWTH_SCALE / (Decimal(10) ** dec1_val))
                    fee_usd = (tok0 * price + tok1) * step_quote_val
                    accrued += fee_usd
                prev_fg0, prev_fg1 = cur0, cur1

                lp_val = position_value_at(
                    price=price,
                    liquidity_human=liquidity_human,
                    entry_price=entry_price,
                    range_pct=range_pct_val,
                    quote_usd_per_token1=step_quote_val,
                )
                nav = compute_nav(
                    wallet=Decimal(str(capital_usd)) - Decimal(str(position_usd)),
                    lp_principal=lp_val.value_usd,
                    accrued_fees=accrued,
                    verified_rewards=Decimal(0),
                    liabilities=Decimal(0),
                )
            except (TypeError, ValueError, InvalidOperation):
                nav = None
                nav_reason = "NAV_COMPUTATION_ERROR"

        step_net_pnl = (net_pnl(nav, prev_nav, Decimal(0))
                        if nav is not None and prev_nav is not None else None)
        if nav is not None:
            prev_nav = nav

        hodl_value: Optional[Decimal] = None
        if open_valid and price is not None and step_quote_val is not None:
            hodl_value = amount0_human * price * step_quote_val + amount1_human * step_quote_val

        insert_row(conn, "rh_gate_decisions", {
            "decision_id": decision.decision_id, "candidate_key": decision.candidate_key,
            "target_mode": decision.target_mode, "primary_status": decision.primary_status,
            "terminal_bits_json": json.dumps(decision.terminal_bits, sort_keys=True),
            "dominant_blocker": decision.dominant_blocker,
            "reasons_json": json.dumps(decision.reasons, sort_keys=True),
            "snapshot_ids_json": json.dumps(decision.snapshot_ids, sort_keys=True),
            "decided_at": decision.decided_at,
        })
        # RH-02bq: persist this step's NetCover economic result.  `gated` was
        # computed above; this row is the only place the economic numbers reach
        # the store.  Fail-close: a sample without a source_payload_hash has no
        # stable snapshot id, so the row is skipped (never fabricated) and the
        # reason is recorded on the step.  No primary-key collision is caught
        # here: a re-run of the same sample across rounds must surface to the
        # daemon layer (RH-02bp), not be silently absorbed.
        snapshot_id = sample.get("source_payload_hash")
        if snapshot_id is not None:
            insert_row(conn, "rh_economic_evaluations", {
                "candidate_key": decision.candidate_key,
                "snapshot_id": snapshot_id,
                # model_version is the gate's versioned model path (e.g.
                # clmm_vol_sized_range_v1); the fallback is a placeholder only
                # if the gate ever omits it.  policy_version is this runner's
                # policy id (the same one reserved above), not a placeholder.
                "model_version": gated.get("netcover_model_path") or "rh_clmm_v1",
                "policy_version": POLICY_ID,
                "horizon_hours": int(horizon_hours),
                "position_usd": str(position_usd),
                "fee_ev": _economic_str(gated.get("fee_ev_usd")),
                "reward_ev": _economic_str(gated.get("reward_ev_usd")),
                "cost_components_json": json.dumps(
                    {k: gated.get(k) for k in _COST_COMPONENT_KEYS},
                    sort_keys=True),
                "netcover": _economic_str(gated.get("netcover")),
                # abs_profit / q_min / q_max have no key in `gated` yet: the
                # absolute-profit decision and the size-interval module are not
                # wired into apply_netcover_gate.  Stored as None, never a value
                # we computed ourselves (fail-close).
                "abs_profit": _economic_str(gated.get("abs_profit")),
                "q_min": _economic_str(gated.get("q_min")),
                "q_max": _economic_str(gated.get("q_max")),
                "missing_inputs_json": json.dumps(
                    gated.get("missing_inputs") or [], sort_keys=True),
                "evaluated_at": decision.decided_at,
                "derived_block_hash": sample.get("derived_block_hash"),
                "derived_block_number": sample.get("derived_block_number"),
            })
        else:
            step_reasons.append("ECONOMIC_EVAL_SKIPPED_NO_SNAPSHOT_ID")
        sample_time = sample.get("sample_time")
        risk_data = {"skipped": nav is None}
        if nav is None and nav_reason is not None:
            risk_data["reason"] = nav_reason
        insert_row(conn, "rh_position_marks", {
            "position_id": f"rh-shadow-{strategy_episode}",
            "mark_time": sample_time if sample_time is not None else now_fn(),
            "price_snapshot_id": None, "reference_nav": nav, "liquidation_nav": None,
            "accrued_fee": accrued if nav is not None else None,
            "unvalued_risk_json": json.dumps(risk_data, sort_keys=True),
        })
        steps.append(ShadowStep(
            i, sample_time, price, eligible, decision.primary_status,
            decision.dominant_blocker, nav, step_net_pnl, hodl_value,
            granted, simulated, tuple(step_reasons), nav_reason))
    return steps


def load_samples_from_db(conn, *, pool: str, limit: int) -> tuple[list[dict], int]:
    """Read the most recent `limit` real samples for `pool` from rh_market_states, replayed in ascending sample_time order; reference_mid IS NULL is skipped and counted (never 0)."""
    cur = conn.execute(
        "SELECT asset_address, sample_time, chain_id, reference_mid, "
        "multiplier_human, session, health_flags_json, reference_age_secs, "
        "oracle_paused, source_payload_hash, reference_bid, reference_ask, "
        "source_event_time, fee_growth_global_0, fee_growth_global_1 "
        "FROM ("
        "SELECT asset_address, sample_time, chain_id, reference_mid, "
        "multiplier_human, session, health_flags_json, reference_age_secs, "
        "oracle_paused, source_payload_hash, reference_bid, reference_ask, "
        "source_event_time, fee_growth_global_0, fee_growth_global_1 "
        "FROM rh_market_states WHERE LOWER(asset_address) = LOWER(?) "
        "ORDER BY sample_time DESC LIMIT ?"
        ") ORDER BY sample_time",
        (pool, limit))
    samples: list[dict] = []
    skipped = 0
    for row in cur.fetchall():
        (asset, st, chain_id, mid, mult, session, flags_json, age,
         oracle_paused, payload_hash, bid, ask, source_event_time,
         fg0, fg1) = row
        if mid is None:
            skipped += 1
            continue
        flags_bools, health_errs = parse_health_flags(flags_json)
        samples.append({
            "asset_address": asset, "sample_time": st, "chain_id": chain_id,
            "reference_mid": Decimal(str(mid)), "multiplier_human": mult,
            # Columns the conjuncts need.  A missing column stays None so the
            # conjunct that needs it fails closed and names itself.
            "session": session,
            "health_flags_json": flags_json,
            "chain_degraded": flags_bools["chain_degraded"],
            "halt": flags_bools["halt"],
            "corp_action_pending": flags_bools["corp_action_pending"],
            "sources_disagree": flags_bools["sources_disagree"],
            "health_flags_errors": health_errs if health_errs else None,
            "reference_age_secs": age,
            "oracle_paused": oracle_paused,
            "source_payload_hash": payload_hash,
            "source_event_time": source_event_time,
            "reference_bid": bid,
            "reference_ask": ask,
            # RH-02ae: fee-growth columns the NAV path reads.  NULL stays None
            # (never 0): run_episode keys its NAV off `is not None`, and 0 would
            # value a sample that carries no fee-growth data.
            "fee_growth_global_0": fg0,
            "fee_growth_global_1": fg1,
        })
    return samples, skipped


def _conjunct_failure_counts(steps) -> dict:
    """Count how often each conjunct named itself as a failure reason."""
    counts: dict = {}
    for step in steps:
        for reason in getattr(step, "conjunct_reasons", ()) or ():
            name = str(reason).split(":", 1)[0].strip()
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def episode_summary(steps: Sequence[ShadowStep], *, load_skipped: int = 0) -> dict:
    """Aggregate an episode into the RH-04b summary dict."""
    status_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    for s in steps:
        status_counts[s.primary_status] = status_counts.get(s.primary_status, 0) + 1
        if s.dominant_blocker is not None:
            blocker_counts[s.dominant_blocker] = blocker_counts.get(s.dominant_blocker, 0) + 1

    # RH-02al: Window alignment over the intersection of steps where both NAV
    # and HODL are available. If HODL is not tracked in the input steps (e.g.
    # isolated NAV tests), fall back to steps where NAV is not None.
    has_hodl = any(s.hodl_value is not None for s in steps)
    if has_hodl:
        valid_steps = [s for s in steps if s.nav is not None and s.hodl_value is not None]
    else:
        valid_steps = [s for s in steps if s.nav is not None]

    window_reason: Optional[str] = None
    if len(valid_steps) >= 2:
        start_step = valid_steps[0]
        end_step = valid_steps[-1]
        nav_start = start_step.nav
        nav_end = end_step.nav
        net_pnl_val = net_pnl(nav_end, nav_start, Decimal(0))
        hodl_delta = (end_step.hodl_value - start_step.hodl_value) if has_hodl else None
        window_start_time = start_step.sample_time
        window_end_time = end_step.sample_time
    elif len(valid_steps) == 1:
        nav_start = valid_steps[0].nav
        nav_end = valid_steps[0].nav
        net_pnl_val = None
        hodl_delta = None
        window_start_time = valid_steps[0].sample_time
        window_end_time = valid_steps[0].sample_time
        window_reason = "INSUFFICIENT_OVERLAPPING_STEPS"
    else:
        nav_start = None
        nav_end = None
        net_pnl_val = None
        hodl_delta = None
        window_start_time = None
        window_end_time = None
        window_reason = "NO_OVERLAPPING_STEPS"

    steps_without_nav_reasons: dict[str, int] = {}
    for s in steps:
        if s.nav is None and getattr(s, "nav_reason", None) is not None:
            r = s.nav_reason
            steps_without_nav_reasons[r] = steps_without_nav_reasons.get(r, 0) + 1

    return {
        "total_steps": len(steps),
        "eligible_steps": sum(1 for s in steps if s.terminal_eligible),
        "status_counts": status_counts, "dominant_blocker_counts": blocker_counts,
        "first_eligible_at": next((s.sample_time for s in steps if s.terminal_eligible), None),
        "nav_start": nav_start, "nav_end": nav_end, "net_pnl": net_pnl_val,
        "hodl_delta": hodl_delta,
        "window_start_time": window_start_time,
        "window_end_time": window_end_time,
        "window_alignment_reason": window_reason,
        # Was one "skipped_samples" field adding these together, which reported
        # 40 when the database held 7 null prices.  They are different facts.
        "skipped_at_load": load_skipped,
        "steps_without_nav": sum(1 for s in steps if s.nav is None),
        "steps_without_nav_reasons": steps_without_nav_reasons,
        # Which conjunct actually failed, not just the roll-up that masks them.
        # legacy_required_conjunction sits first in CONJUNCT_ORDER so it always
        # takes the blame; these counts say what it was waiting on.
        "conjunct_failure_counts": _conjunct_failure_counts(steps),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RH-04b Shadow runner (read-only).")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--target-mode", default="SHADOW_SCENARIO",
                   choices=["SHADOW_SCENARIO", "LIVE_READINESS"])
    p.add_argument("--pool", default=DEFAULT_POOL)
    p.add_argument("--out", default=None)
    p.add_argument("--pool-meta-json", default=None,
                   help="JSON file with pool evidence: attestation_status, protocol, "
                        "sqrt_price_x96, current_tick, tick_spacing, fee_pips, "
                        "liquidity, tick_data, token0_decimals, token1_decimals, "
                        "input_price_usd.  Without it the conjuncts that need pool "
                        "state fail closed and say so.")
    p.add_argument("--allow-bare-quote", action="store_true", default=False,
                   help="Allow bare numbers for quote_usd_per_token1 without "
                        "provenance or TTL check (default False: fails closed).")
    a = p.parse_args(argv)

    live_conn = open_store(Path(a.db), read_only=True)
    try:
        samples, load_skipped = load_samples_from_db(live_conn, pool=a.pool, limit=a.samples)
        pool_meta = None
        if a.pool_meta_json:
            with open(a.pool_meta_json, "r", encoding="utf-8") as fh:
                pool_meta = json.load(fh)
    finally:
        live_conn.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        sc = open_store(Path(tmpdir) / "scratch.db", read_only=False)
        migrate(sc)
        now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        ep = "rh-shadow-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        steps = run_episode(sc, strategy_episode=ep, samples=samples,
                            position_usd=Decimal("1000"), horizon_hours=24.0,
                            capital_usd=Decimal("10000"), target_mode=a.target_mode,
                            now_fn=now, pool_meta=pool_meta,
                            allow_bare_quote=a.allow_bare_quote)
        sc.close()

    payload = {"target_mode": a.target_mode, "pool": a.pool, "strategy_episode": ep,
               "steps": [asdict(s) for s in steps],
               "summary": episode_summary(steps, load_skipped=load_skipped)}
    out_text = json.dumps(payload, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(out_text)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
