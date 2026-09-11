#!/usr/bin/env python3
"""RH-04b: single-CORE-pool Shadow runner (orchestration only, read-only).

Wires the six RH layers into one replayable, offline-testable Shadow closed
loop.  Calls existing modules; adds no economic logic.  Live store opened
read-only; all Shadow writes go to a scratch store.  No wallet, no broadcast.
"""
import argparse
import json
import math
import sqlite3
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

from scripts.lp_rh_gas_estimator_v1_readonly import observed_gas_usd
from scripts.lp_rh_gas_reserve_v1_readonly import (
    exit_gas_requirement_usd,
    native_reserve_gate,
    wrapped_does_not_count,
)
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
    release,
    reserved_total,
    try_reserve,
)
from scripts.lp_rh_size_interval_v1_readonly import size_interval
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID
from scripts.lp_rh_market_session_v1_readonly import (
    allows_new_position,
    classify_session,
    evaluate_health,
)
from scripts.lp_rh_in_range_v1_readonly import tick_from_price
from scripts.lp_rh_exit_depth_v1_readonly import exit_depth_for_size
from scripts.lp_rh_pnl_v1_readonly import (
    book_journal_event,
    compute_nav,
    hodl_benchmark,
    net_pnl,
)
from scripts.lp_rh_store_v1_readonly import (
    assert_utc_rfc3339,
    insert_row,
    migrate,
    open_store,
)
from scripts.lp_rh_v3_inventory_v1_readonly import (
    inventory_for_position,
    position_value_at,
)

# Uniswap V3 fee-growth scaling: fees = L * delta(feeGrowthGlobal) / 2**128.
FEE_GROWTH_SCALE = Decimal(2) ** 128
DEFAULT_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
DEFAULT_DB = "reports/lp_rh/scanner.db"
DEFAULT_GAS_DB = "reports/lp_rh/gas_history.db"
DEFAULT_ORGANIC_DB = "reports/lp_rh/organic.db"
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
    gas_usd_source: Optional[str] = None
    gas_reserve: Optional[dict] = None
    size_interval: Optional[dict] = None
    in_range: Optional[bool] = None
    organic: Optional[dict] = None


def _candidate_key(sample: Mapping[str, Any], step_index: int) -> str:
    """Per-step unique candidate key so decision_id (PK) never collides."""
    base = (sample.get("candidate_key") or sample.get("pool_key")
            or sample.get("asset_address") or "pool")
    st = sample.get("sample_time")
    return f"{base}@{st}" if st else f"{base}#{step_index}"


def _terminal_record(sample, gated, step_index, *, pool_meta=None,
                    capital_usd=None, position_usd=None, now=None,
                    conjunct_reasons=None, strategy_episode=None) -> dict:
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
    if strategy_episode:
        rec["strategy_episode"] = strategy_episode
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
    "observed_gas_usd",
)


# RH-02bq: the eight cost/risk components that sum to the NetCover model's
# expected_risk_cost.  Persisted verbatim (as JSON) so the full-cost breakdown
# is auditable, not just the NetCover ratio.
_COST_COMPONENT_KEYS = (
    "il_ev_usd", "lvr_ev_usd", "entry_cost_usd", "exit_cost_usd",
    "gas_usd", "slippage_usd", "reward_conversion_cost_usd",
    "exit_latency_loss_usd",
)

POSITION_TVL_SHARE = Decimal("0.0005")


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


def compute_size_interval(
    conn: sqlite3.Connection,
    *,
    gated: Mapping[str, Any],
    capital_usd: Any,
    position_usd: Any,
    pool_meta: Optional[Mapping[str, Any]],
    gas_reserve_result: Optional[Mapping[str, Any]],
) -> dict:
    """Compute q_min and partial q_max, classifying the feasibility interval (RH-02cl / T31)."""
    # 1. q_min computation
    q_min: Optional[Decimal] = None
    q_min_reason: Optional[str] = None
    costs = {k: gated.get(k) for k in _COST_COMPONENT_KEYS}
    fee_ev = gated.get("fee_ev_usd")
    # No default here: apply_netcover_gate always sets reward_ev_usd (0.0 when
    # the reward is unverified or absent, per T33 -- advertised APR is not
    # verified income). The None case is handled once, below, where the Decimal
    # is built. A second default here would only hide a genuinely missing key.
    reward_ev = gated.get("reward_ev_usd")

    if any(v is None for v in costs.values()) or fee_ev is None or position_usd is None:
        q_min = None
        q_min_reason = "INPUTS_MISSING"
    else:
        try:
            pos_dec = Decimal(str(position_usd))
            if pos_dec <= Decimal(0):
                q_min = None
                q_min_reason = "POSITION_USD_NON_POSITIVE"
            else:
                fee_ev_dec = Decimal(str(fee_ev))
                reward_ev_dec = Decimal(str(reward_ev)) if reward_ev is not None else Decimal(0)
                il_ev_dec = Decimal(str(costs["il_ev_usd"]))
                lvr_ev_dec = Decimal(str(costs["lvr_ev_usd"]))
                slippage_dec = Decimal(str(costs["slippage_usd"]))
                exit_latency_dec = Decimal(str(costs["exit_latency_loss_usd"]))
                reward_conversion_dec = Decimal(str(costs["reward_conversion_cost_usd"]))

                entry_cost_dec = Decimal(str(costs["entry_cost_usd"]))
                exit_cost_dec = Decimal(str(costs["exit_cost_usd"]))
                gas_cost_dec = Decimal(str(costs["gas_usd"]))

                variable_costs = (
                    il_ev_dec
                    + lvr_ev_dec
                    + slippage_dec
                    + exit_latency_dec
                    + reward_conversion_dec
                )
                per_dollar_net = (
                    fee_ev_dec + reward_ev_dec - variable_costs
                ) / pos_dec
                fixed_round_trip = entry_cost_dec + exit_cost_dec + gas_cost_dec

                if per_dollar_net <= Decimal(0):
                    q_min = None
                    q_min_reason = "NO_SIZE_IS_PROFITABLE"
                else:
                    q_min = fixed_round_trip / per_dollar_net
        except (TypeError, ValueError, InvalidOperation) as exc:
            q_min = None
            q_min_reason = f"CALCULATION_ERROR:{type(exc).__name__}"

    # 2. q_max computation (partial constraints)
    applied_constraints: list[str] = []
    missing_constraints: list[str] = [
        "global_active_room",
        "approved_position_cap",
        "asset_exposure_room",
    ]
    candidate_limits: list[tuple[Decimal, str]] = []

    # Constraint 1: bucket_active_room
    try:
        cap_val = bucket_active_cap(Decimal(str(capital_usd)), "CORE")
        res_val = reserved_total(conn, "CORE", POLICY_ID)
        room = Decimal(str(cap_val)) - Decimal(str(res_val))
        candidate_limits.append((room, "bucket_active_room"))
        applied_constraints.append("bucket_active_room")
    except Exception:
        missing_constraints.append("bucket_active_room")

    # Constraint 2: POSITION_TVL_SHARE * TVL
    tvl_raw = pool_meta.get("tvl_usd") if pool_meta else None
    if tvl_raw is not None:
        try:
            tvl_dec = Decimal(str(tvl_raw))
            candidate_limits.append((POSITION_TVL_SHARE * tvl_dec, "tvl_share"))
            applied_constraints.append("tvl_share")
        except (TypeError, ValueError, InvalidOperation):
            missing_constraints.append("tvl_share")
    else:
        missing_constraints.append("tvl_share")

    # Constraint 3: measured_exit_depth_cap
    exit_depth_val: Optional[Decimal] = None
    if pool_meta and pool_meta.get("tick_data") and pool_meta.get("max_impact_bps") is not None:
        try:
            depth_dict = exit_depth_for_size(
                position_value_usd=Decimal(str(position_usd)),
                max_impact_bps=Decimal(str(pool_meta["max_impact_bps"])),
                **{k: v for k, v in pool_meta.items()
                   if k not in ("attestation_status", "protocol", "max_impact_bps", "_gas_reserve_result")}
            )
            raw_max_exit = depth_dict.get("max_exit_usd")
            if raw_max_exit is not None:
                exit_depth_val = Decimal(str(raw_max_exit))
        except Exception:
            exit_depth_val = None

    if exit_depth_val is not None:
        candidate_limits.append((exit_depth_val, "measured_exit_depth_cap"))
        applied_constraints.append("measured_exit_depth_cap")
    else:
        missing_constraints.append("measured_exit_depth_cap")

    # Constraint 4: spendable_cash_after_native_gas_reserve
    gas_req = gas_reserve_result.get("required_usd") if gas_reserve_result else None
    if gas_req is not None and capital_usd is not None:
        try:
            spendable = Decimal(str(capital_usd)) - Decimal(str(gas_req))
            candidate_limits.append((spendable, "spendable_cash_after_native_gas_reserve"))
            applied_constraints.append("spendable_cash_after_native_gas_reserve")
        except (TypeError, ValueError, InvalidOperation):
            missing_constraints.append("spendable_cash_after_native_gas_reserve")
    else:
        missing_constraints.append("spendable_cash_after_native_gas_reserve")

    if candidate_limits:
        candidate_limits.sort(key=lambda item: item[0])
        q_max, q_max_binding = candidate_limits[0]
    else:
        q_max, q_max_binding = None, None

    interval_result = size_interval(q_min=q_min, q_max=q_max)

    combined_reason = interval_result["reason"]
    if q_min is None and q_min_reason is not None:
        combined_reason = f"{combined_reason}; q_min unavailable: {q_min_reason}"

    return {
        "status": interval_result["status"],
        "q_min": interval_result["q_min"],
        "q_max": interval_result["q_max"],
        "width": interval_result["width"],
        "reason": combined_reason,
        "q_max_binding": q_max_binding,
        "q_max_constraints_applied": applied_constraints,
        "q_max_constraints_missing": sorted(missing_constraints),
        "q_max_is_partial": True,
    }


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


def _find_closest_organic_window(windows: Sequence[dict], sample_time: Any) -> Optional[dict]:
    """Find the closest organic window not later than sample_time (RH-02cn)."""
    step_dt = _as_datetime(sample_time)
    if step_dt is None or not windows:
        return None
    candidates = [w for w in windows if w["dt"] <= step_dt]
    if not candidates:
        return None
    return candidates[-1]


def resolve_organic_discount(window: Optional[dict]) -> tuple[str, Optional[Decimal]]:
    """Determine organic discount status and fraction according to RH-02cn.

    Fail-close conditions:
      - Window missing -> ORGANIC_UNAVAILABLE:NO_WINDOW
      - estimate_status != 'COMPUTED' -> ORGANIC_UNAVAILABLE:<status>
      - coverage_frac < 1 -> ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE
      - organic_fraction is None or not in (0, 1] -> ORGANIC_UNAVAILABLE:INVALID_FRACTION

    Returns (status, fraction). When valid, status is 'OK' and fraction is Decimal.
    When fail-close, fraction is None (never defaulted to 1.0).
    """
    if window is None:
        return "ORGANIC_UNAVAILABLE:NO_WINDOW", None

    status = window.get("estimate_status")
    if status != "COMPUTED":
        status_tag = status if status is not None else "NONE"
        return f"ORGANIC_UNAVAILABLE:{status_tag}", None

    cov_val = window.get("coverage_frac")
    if cov_val is None:
        return "ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE", None
    try:
        cov = Decimal(str(cov_val))
        if cov < Decimal("1"):
            return "ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE", None
    except Exception:
        return "ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE", None

    frac_val = window.get("organic_fraction")
    if frac_val is None:
        return "ORGANIC_UNAVAILABLE:INVALID_FRACTION", None
    try:
        frac = Decimal(str(frac_val))
        if frac <= Decimal("0") or frac > Decimal("1"):
            return "ORGANIC_UNAVAILABLE:INVALID_FRACTION", None
    except Exception:
        return "ORGANIC_UNAVAILABLE:INVALID_FRACTION", None

    return "OK", frac


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
    #
    # RH-02bt: max_impact_bps used to fall back to 50 when the key was absent.
    # That turned a risk gate into a rubber stamp on a single config omission --
    # no error, no log line, just a permissive threshold nobody chose.  Missing
    # tolerance is unknown tolerance, so it fails closed like tick_data does.
    # Tested with `is None`, not falsiness: 0 bps is a legitimate (if
    # unsatisfiable) tolerance and must not be mistaken for a missing key.
    if not pool_meta or not pool_meta.get("tick_data"):
        fail("position_and_exit_depth_pass", "pool_meta lacks tick_data")
    elif pool_meta.get("max_impact_bps") is None:
        fail("position_and_exit_depth_pass", "pool_meta lacks max_impact_bps")
    else:
        depth = exit_depth_for_size(
            position_value_usd=Decimal(str(position_usd)),
            max_impact_bps=Decimal(str(pool_meta["max_impact_bps"])),
            **{k: v for k, v in pool_meta.items()
               if k not in ("attestation_status", "protocol", "max_impact_bps")})
        if depth.get("sufficient"):
            # RH-02ck: if enforce_gas_reserve is True, insufficient native gas reserve fails position_and_exit_depth_pass
            gas_res = pool_meta.get("_gas_reserve_result") if pool_meta else None
            if gas_res and gas_res.get("enforce") and not gas_res.get("pass"):
                fail("position_and_exit_depth_pass", f"NATIVE_GAS_RESERVE_INSUFFICIENT:{gas_res.get('reason')}")
            else:
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
                allow_bare_quote=False, gas_db_path=DEFAULT_GAS_DB,
                enforce_gas_reserve=False, organic_db_path=DEFAULT_ORGANIC_DB):
    """Replay one Shadow episode over `samples`, writing gate decisions and position marks to `conn`."""
    # RH-02cg: take gas observation once per episode (not per step).
    effective_pool_meta = dict(pool_meta) if pool_meta else {}
    episode_now = now_fn() if callable(now_fn) else str(now_fn)

    # RH-02cn: load organic windows once per episode
    organic_windows: list[dict] = []
    if organic_db_path and Path(organic_db_path).exists():
        try:
            org_conn = sqlite3.connect(f"file:{organic_db_path}?mode=ro", uri=True)
            try:
                cur = org_conn.execute(
                    "SELECT sample_time, organic_fraction, coverage_frac, estimate_status "
                    "FROM rh_organic_windows"
                )
                for st, frac, cov, est_stat in cur.fetchall():
                    dt = _as_datetime(st)
                    if dt is not None:
                        organic_windows.append({
                            "sample_time": st,
                            "dt": dt,
                            "organic_fraction": frac,
                            "coverage_frac": cov,
                            "estimate_status": est_stat,
                        })
                organic_windows.sort(key=lambda w: w["dt"])
            finally:
                org_conn.close()
        except Exception:
            pass

    # RH-02ck: gas reserve check once per episode
    # 1) Fetch gas_price_wei and native_price_usd from gas_db
    # 2) Call exit_gas_requirement_usd
    # 3) Call native_reserve_gate and wrapped_does_not_count
    gas_reserve_result = {
        "required_usd": None,
        "sufficient": False,
        "reason": "GAS_DB_UNAVAILABLE",
        "enforced": bool(enforce_gas_reserve),
        "native_balance_known": False,
        "pass": False,
        "enforce": bool(enforce_gas_reserve),
    }
    latest_gas_obs = None
    if gas_db_path and Path(gas_db_path).exists():
        try:
            gas_conn = sqlite3.connect(f"file:{gas_db_path}?mode=ro", uri=True)
            try:
                obs = observed_gas_usd(gas_conn, now=episode_now)
                if obs.get("reason") == "OK" and obs.get("gas_usd") is not None:
                    effective_pool_meta["observed_gas_usd"] = float(obs["gas_usd"])

                # Fetch latest gas observation for gas reserve calculation
                cur = gas_conn.execute(
                    "SELECT gas_price_wei, native_price_usd FROM rh_gas_observations "
                    "ORDER BY observed_at DESC LIMIT 1"
                )
                latest_gas_obs = cur.fetchone()
            finally:
                gas_conn.close()
        except Exception:
            pass

    native_balance_wei = effective_pool_meta.get("native_balance_wei")
    weth_balance_wei = effective_pool_meta.get("weth_balance_wei")
    native_balance_known = native_balance_wei is not None

    if latest_gas_obs is not None and latest_gas_obs[0] is not None and latest_gas_obs[1] is not None:
        g_price_wei, n_price_usd = latest_gas_obs[0], latest_gas_obs[1]
        req_usd = exit_gas_requirement_usd(gas_price_wei=g_price_wei, native_price_usd=n_price_usd)
        gate_res = native_reserve_gate(
            native_balance_wei=native_balance_wei,
            gas_price_wei=g_price_wei,
            native_price_usd=n_price_usd,
        )
        wrapped_res = wrapped_does_not_count(
            weth_balance_wei=weth_balance_wei,
            native_balance_wei=native_balance_wei,
        )
        reason = gate_res.get("reason")
        if weth_balance_wei is not None and native_balance_wei is None:
            reason = f"{reason}:{wrapped_res.get('note')}"

        req_usd_str = str(req_usd) if req_usd is not None else (str(gate_res["required_usd"]) if gate_res.get("required_usd") is not None else None)
        sufficient = bool(gate_res.get("pass"))

        gas_reserve_result = {
            "required_usd": req_usd_str,
            "sufficient": sufficient,
            "reason": reason,
            "enforced": bool(enforce_gas_reserve),
            "native_balance_known": native_balance_known,
            "pass": sufficient,
            "enforce": bool(enforce_gas_reserve),
        }
    else:
        req_usd_str = None
        wrapped_res = wrapped_does_not_count(
            weth_balance_wei=weth_balance_wei,
            native_balance_wei=native_balance_wei,
        )
        reason = "GAS_DB_UNAVAILABLE" if not (gas_db_path and Path(gas_db_path).exists()) else "GAS_OBSERVATIONS_UNAVAILABLE"
        if weth_balance_wei is not None and native_balance_wei is None:
            reason = f"{reason}:{wrapped_res.get('note')}"

        gas_reserve_result = {
            "required_usd": None,
            "sufficient": False,
            "reason": reason,
            "enforced": bool(enforce_gas_reserve),
            "native_balance_known": native_balance_known,
            "pass": False,
            "enforce": bool(enforce_gas_reserve),
        }

    effective_pool_meta["_gas_reserve_result"] = gas_reserve_result

    steps: list[ShadowStep] = []
    position_open = False
    prev_nav: Optional[Decimal] = None
    prev_fg0: Optional[Decimal] = None
    prev_fg1: Optional[Decimal] = None
    accrued = Decimal(0)
    accrued_raw = Decimal(0)
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
    # RH-02bu-2: virtual-open persistence state.  The reservation grant (event A)
    # and the inventory resolution (event B) land on different steps, so the
    # row is written at the end of the loop, once both are available.
    position_row_written = False
    pending_position_open_at: Optional[str] = None
    inv_cached = None
    tick_lower: Optional[int] = None
    tick_upper: Optional[int] = None

    for i, sample in enumerate(samples):
        record = assemble_rh_clmm_inputs(_evidence_for(sample, effective_pool_meta),
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
            _terminal_record(sample, gated, i, pool_meta=effective_pool_meta,
                             capital_usd=capital_usd, position_usd=position_usd,
                             now=decision_now, conjunct_reasons=step_reasons,
                             strategy_episode=strategy_episode),
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
                pending_position_open_at = decision_now

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
                        inv_cached = inv
                        p_lower = price * (Decimal(1) - r_pct / Decimal(100))
                        p_upper = price * (Decimal(1) + r_pct / Decimal(100))
                        t_a = tick_from_price(p_lower, dec0=d0, dec1=d1)
                        t_b = tick_from_price(p_upper, dec0=d0, dec1=d1)
                        tick_lower = min(t_a, t_b)
                        tick_upper = max(t_a, t_b)
                    else:
                        open_fail_reason = open_fail_reason or "RANGE_OR_INPUTS_INVALID"
                except (TypeError, ValueError, InvalidOperation):
                    open_valid = False
            else:
                open_valid = False
                open_fail_reason = "RANGE_PCT_MISSING"

        step_in_range: Optional[bool] = None
        if price is not None and tick_lower is not None and tick_upper is not None:
            try:
                t = tick_from_price(price, dec0=dec0_val, dec1=dec1_val)
                step_in_range = bool(tick_lower <= t < tick_upper)
            except (TypeError, ValueError, InvalidOperation):
                step_in_range = None

        # RH-02cn: resolve organic window for this step
        step_window = _find_closest_organic_window(organic_windows, sample.get("sample_time"))
        organic_status, organic_fraction = resolve_organic_discount(step_window)
        fee_usd_raw: Optional[Decimal] = None
        fee_usd_organic: Optional[Decimal] = None

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
                    fee_usd_raw = (tok0 * price + tok1) * step_quote_val
                    if organic_status == "OK" and organic_fraction is not None:
                        fee_usd_organic = fee_usd_raw * organic_fraction
                    else:
                        fee_usd_organic = fee_usd_raw
                    fee_usd = fee_usd_organic
                    if step_in_range is True:
                        accrued += fee_usd
                        accrued_raw += fee_usd_raw
                else:
                    fee_usd_raw = Decimal(0)
                    fee_usd_organic = Decimal(0)
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
                fee_usd_raw = None
                fee_usd_organic = None

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
        # RH-02cl: compute economic feasibility interval [q_min, q_max]
        size_interval_res = compute_size_interval(
            conn,
            gated=gated,
            capital_usd=capital_usd,
            position_usd=position_usd,
            pool_meta=effective_pool_meta,
            gas_reserve_result=gas_reserve_result,
        )

        # RH-02bq: persist this step's NetCover economic result.  `gated` was
        # computed above; this row is the only place the economic numbers reach
        # the store.  Fail-close: a sample without a source_payload_hash has no
        # stable snapshot id, so the row is skipped (never fabricated) and the
        # reason is recorded on the step.  No primary-key collision is caught
        # here: a re-run of the same sample across rounds must surface to the
        # daemon layer (RH-02bp), not be silently absorbed.
        snapshot_id = sample.get("source_payload_hash")
        if snapshot_id is not None:
            size_interval_meta = {
                "status": size_interval_res["status"],
                "width": float(size_interval_res["width"]) if size_interval_res.get("width") is not None else None,
                "reason": size_interval_res.get("reason"),
                "q_max_binding": size_interval_res.get("q_max_binding"),
                "q_max_constraints_applied": size_interval_res.get("q_max_constraints_applied"),
                "q_max_constraints_missing": size_interval_res.get("q_max_constraints_missing"),
                "q_max_is_partial": size_interval_res.get("q_max_is_partial", True),
            }
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
                    dict(
                        {k: gated.get(k) for k in _COST_COMPONENT_KEYS},
                        gas_usd_source=gated.get("gas_usd_source"),
                        exit_gas_reserve_usd=float(gas_reserve_result["required_usd"]) if gas_reserve_result.get("required_usd") is not None else None,
                        size_interval=size_interval_meta,
                    ),
                    sort_keys=True),
                "netcover": _economic_str(gated.get("netcover")),
                # abs_profit has no key in `gated` yet: the absolute-profit
                # decision is not wired into apply_netcover_gate.
                # q_min / q_max are computed by compute_size_interval (RH-02cl).
                "abs_profit": _economic_str(gated.get("abs_profit")),
                "q_min": _economic_str(size_interval_res.get("q_min")),
                "q_max": _economic_str(size_interval_res.get("q_max")),
                "missing_inputs_json": json.dumps(
                    gated.get("missing_inputs") or [], sort_keys=True),
                "evaluated_at": decision.decided_at,
                "derived_block_hash": sample.get("derived_block_hash"),
                "derived_block_number": sample.get("derived_block_number"),
            })
        else:
            step_reasons.append("ECONOMIC_EVAL_SKIPPED_NO_SNAPSHOT_ID")
        sample_time = sample.get("sample_time")
        risk_data = {
            "skipped": nav is None,
            "liquidation_nav_reason": "NOT_COMPUTED:EXIT_DEPTH_PER_STEP_NOT_WIRED",
            "in_range": step_in_range,
            "fee_usd_raw": _economic_str(fee_usd_raw),
            "fee_usd_organic": _economic_str(fee_usd_organic),
            "organic_fraction": _economic_str(organic_fraction),
            "organic_status": organic_status,
        }
        if nav is None and nav_reason is not None:
            risk_data["reason"] = nav_reason
        insert_row(conn, "rh_position_marks", {
            "position_id": f"rh-shadow-{strategy_episode}",
            "mark_time": sample_time if sample_time is not None else now_fn(),
            "price_snapshot_id": sample.get("source_payload_hash"),
            "reference_nav": nav,
            "liquidation_nav": None,
            "accrued_fee": accrued if nav is not None else None,
            "unvalued_risk_json": json.dumps(risk_data, sort_keys=True),
            "derived_block_hash": sample.get("derived_block_hash"),
            "derived_block_number": sample.get("derived_block_number"),
        })
        # RH-02bu-2: persist the virtual open position, at most one row per
        # episode.  The quantities come from the inventory-resolution step
        # (the episode's open assumption -- the HODL benchmark uses the same
        # numbers); opened_at comes from the reservation-grant step.  The two
        # may land on different steps; that is the existing shape of the
        # economic model and this writer only records it, it does not change
        # the model.  The _raw values are Decimals that may carry a fractional
        # part, so they are stored via str() verbatim -- int() truncation
        # would diverge from the values NAV uses.  No pool key means no row
        # (pool_key is NOT NULL), never an empty-string placeholder.  A PK
        # collision on a cross-round re-run is deliberately NOT caught here:
        # it surfaces to the daemon layer (_run_episode_persisted), the same
        # way rh_economic_evaluations collisions do.
        if (pending_position_open_at is not None and not position_row_written
                and open_valid and inv_cached is not None):
            pool_key = None
            if pool_meta is not None:
                pool_key = pool_meta.get("pool_address") or pool_meta.get("pool_key")
            if pool_key is None:
                pool_key = sample.get("asset_address")
            if pool_key:
                insert_row(conn, "rh_shadow_positions", {
                    "strategy_episode": strategy_episode,
                    "position_id": f"rh-shadow-{strategy_episode}",
                    "pool_key": pool_key,
                    "profile": "CORE",
                    "bucket": "CORE",
                    "initial_token0_raw": str(inv_cached.amount0_raw),
                    "initial_token1_raw": str(inv_cached.amount1_raw),
                    "virtual_liquidity_raw": str(inv_cached.liquidity_raw),
                    "tick_lower": tick_lower,
                    "tick_upper": tick_upper,
                    "opened_at": pending_position_open_at,
                    "closed_at": None,
                })
                position_row_written = True
                # RH-02by: book the virtual open as a two-leg double-entry
                # journal entry (assets move wallet -> LP position).  Each leg
                # is one row.  NOTE: rh_journal's PRIMARY KEY is event_id, so
                # the two legs cannot share one event_id (the spec's literal
                # f"{strategy_episode}-open" would violate that primary key);
                # each leg therefore carries its own event_id.  Each row is
                # self-balancing (one debit + one credit account, same amount),
                # so the Stage B balance audit (audit_unexplained_ledger_diffs)
                # still reports count == 0.  is_external_flow=False: this is an
                # internal transfer, not external funding (PRD D03 -- marking it
                # external would pollute PnL attribution).  The asset field must
                # be the real token address; a missing address means no journal
                # row, never a pool address / empty string / placeholder.  A
                # duplicate idempotency_key on a cross-round re-run is
                # deliberately NOT caught here (RH-INV-13): it surfaces to the
                # daemon layer (_run_episode_persisted), the same way the
                # position row does.
                tok0 = pool_meta.get("token0") if pool_meta else None
                tok1 = pool_meta.get("token1") if pool_meta else None
                if tok0 is not None and tok1 is not None:
                    book_journal_event(
                        conn,
                        event_id=f"{strategy_episode}-open-token0",
                        idempotency_key=f"{strategy_episode}-open-token0",
                        debit="LP_POSITION_TOKEN0",
                        credit="WALLET_TOKEN0",
                        asset=tok0,
                        amount_raw=inv_cached.amount0_raw,
                        is_external_flow=False,
                        ref={"position_id": f"rh-shadow-{strategy_episode}",
                             "leg": "token0",
                             "opened_at": pending_position_open_at},
                        now=pending_position_open_at,
                    )
                    book_journal_event(
                        conn,
                        event_id=f"{strategy_episode}-open-token1",
                        idempotency_key=f"{strategy_episode}-open-token1",
                        debit="LP_POSITION_TOKEN1",
                        credit="WALLET_TOKEN1",
                        asset=tok1,
                        amount_raw=inv_cached.amount1_raw,
                        is_external_flow=False,
                        ref={"position_id": f"rh-shadow-{strategy_episode}",
                             "leg": "token1",
                             "opened_at": pending_position_open_at},
                        now=pending_position_open_at,
                    )
                else:
                    step_reasons.append("JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES")
            else:
                step_reasons.append("SHADOW_POSITION_NOT_RECORDED:NO_POOL_KEY")
        steps.append(ShadowStep(
            i, sample_time, price, eligible, decision.primary_status,
            decision.dominant_blocker, nav, step_net_pnl, hodl_value,
            granted, simulated, tuple(step_reasons), nav_reason,
            gated.get("gas_usd_source"),
            gas_reserve={
                "required_usd": gas_reserve_result.get("required_usd"),
                "sufficient": gas_reserve_result.get("sufficient"),
                "reason": gas_reserve_result.get("reason"),
                "enforced": gas_reserve_result.get("enforced"),
                "native_balance_known": gas_reserve_result.get("native_balance_known"),
            },
            size_interval=size_interval_res,
            in_range=step_in_range,
            organic={
                "status": organic_status,
                "fraction": organic_fraction,
                "fee_usd_raw": fee_usd_raw,
                "fee_usd_organic": fee_usd_organic,
                "accrued_raw": accrued_raw,
                "accrued_organic": accrued,
            }))

    if position_open:
        release_now = None
        if steps and steps[-1].sample_time:
            try:
                release_now = assert_utc_rfc3339(steps[-1].sample_time, "sample_time")
            except (ValueError, TypeError):
                release_now = None
        if release_now is None:
            release_now = now_fn()

        granted_step = next((s for s in steps if s.reservation_granted), None)
        if granted_step is not None:
            intent_id = f"rh-shadow-{strategy_episode}-{granted_step.step_index}"
            released = release(
                conn,
                intent_id=intent_id,
                now=release_now,
                reason="SHADOW_EPISODE_COMPLETE",
            )
            if not released:
                reasons = list(steps[-1].conjunct_reasons)
                reasons.append("RESERVATION_RELEASE_FAILED:INTENT_NOT_FOUND")
                steps[-1].conjunct_reasons = tuple(reasons)
                if granted_step is not steps[-1]:
                    g_reasons = list(granted_step.conjunct_reasons)
                    g_reasons.append("RESERVATION_RELEASE_FAILED:INTENT_NOT_FOUND")
                    granted_step.conjunct_reasons = tuple(g_reasons)

        # RH-02ci: book fee accrual into rh_journal at episode close
        if accrued > 0:
            fee_quote = None
            fee_dec1 = None
            if pool_meta:
                raw_quote = pool_meta.get("quote_usd_per_token1")
                if raw_quote is not None:
                    last_time = steps[-1].sample_time if steps else None
                    q_val, _ = validate_quote_evidence(
                        raw_quote,
                        sample_time=last_time,
                        allow_bare_quote=allow_bare_quote,
                    )
                    if q_val is not None and q_val > 0:
                        fee_quote = q_val
                d1_raw = pool_meta.get("dec1", pool_meta.get("token1_decimals"))
                if d1_raw is not None:
                    try:
                        d1_int = int(d1_raw)
                        if d1_int >= 0:
                            fee_dec1 = d1_int
                    except (TypeError, ValueError):
                        fee_dec1 = None

            if fee_quote is not None and fee_dec1 is not None:
                tok1 = pool_meta.get("token1") if pool_meta else None
                if tok1 is not None:
                    fee_amount_raw = (accrued / fee_quote) * (Decimal(10) ** fee_dec1)
                    book_journal_event(
                        conn,
                        event_id=f"{strategy_episode}-fees",
                        idempotency_key=f"{strategy_episode}-fees",
                        debit="LP_FEES_RECEIVABLE",
                        credit="LP_FEE_INCOME",
                        asset=tok1,
                        amount_raw=fee_amount_raw,
                        is_external_flow=False,
                        ref={
                            "position_id": f"rh-shadow-{strategy_episode}",
                            "kind": "fee_accrual",
                            "steps": len(steps),
                            "accrued_usd": str(accrued),
                        },
                        now=release_now,
                    )
                else:
                    if steps:
                        reasons = list(steps[-1].conjunct_reasons)
                        reasons.append("FEE_JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES")
                        steps[-1].conjunct_reasons = tuple(reasons)
                        if granted_step is not None and granted_step is not steps[-1]:
                            g_reasons = list(granted_step.conjunct_reasons)
                            g_reasons.append("FEE_JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES")
                            granted_step.conjunct_reasons = tuple(g_reasons)
            else:
                if steps:
                    reasons = list(steps[-1].conjunct_reasons)
                    reasons.append("FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1")
                    steps[-1].conjunct_reasons = tuple(reasons)
                    if granted_step is not None and granted_step is not steps[-1]:
                        g_reasons = list(granted_step.conjunct_reasons)
                        g_reasons.append("FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1")
                        granted_step.conjunct_reasons = tuple(g_reasons)
        elif accrued == 0:
            if steps:
                reasons = list(steps[-1].conjunct_reasons)
                reasons.append("FEE_JOURNAL_NOT_BOOKED:ZERO_ACCRUED")
                steps[-1].conjunct_reasons = tuple(reasons)
                if granted_step is not None and granted_step is not steps[-1]:
                    g_reasons = list(granted_step.conjunct_reasons)
                    g_reasons.append("FEE_JOURNAL_NOT_BOOKED:ZERO_ACCRUED")
                    granted_step.conjunct_reasons = tuple(g_reasons)

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


def episode_summary(steps: Sequence[ShadowStep], *, load_skipped: int = 0, pool_meta: Optional[dict] = None) -> dict:
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
    size_interval_status_counts: dict[str, int] = {}
    in_range_steps = 0
    out_of_range_steps = 0
    skipped_no_price = 0
    summary_tick_lower: Optional[int] = None
    summary_tick_upper: Optional[int] = None

    for s in steps:
        if getattr(s, "in_range", None) is True:
            in_range_steps += 1
        elif getattr(s, "in_range", None) is False:
            out_of_range_steps += 1
        else:
            skipped_no_price += 1

        if s.nav is None and getattr(s, "nav_reason", None) is not None:
            r = s.nav_reason
            steps_without_nav_reasons[r] = steps_without_nav_reasons.get(r, 0) + 1
        s_int = getattr(s, "size_interval", None)
        if s_int and isinstance(s_int, dict) and s_int.get("status"):
            st = str(s_int["status"])
            size_interval_status_counts[st] = size_interval_status_counts.get(st, 0) + 1

    denom = in_range_steps + out_of_range_steps
    in_range_fraction_val = (Decimal(in_range_steps) / Decimal(denom)) if denom > 0 else None

    # Derive tick_lower / tick_upper from open step if pool_meta and entry price are present
    open_step = next((s for s in steps if s.price is not None and s.price > 0), None)
    if open_step is not None and pool_meta is not None and "range_pct" in pool_meta:
        try:
            r_pct = Decimal(str(pool_meta["range_pct"]))
            d0_raw = pool_meta.get("dec0", pool_meta.get("token0_decimals"))
            d1_raw = pool_meta.get("dec1", pool_meta.get("token1_decimals"))
            if d0_raw is not None and d1_raw is not None and 0 < r_pct < 100:
                d0 = int(d0_raw)
                d1 = int(d1_raw)
                p_lower = open_step.price * (Decimal(1) - r_pct / Decimal(100))
                p_upper = open_step.price * (Decimal(1) + r_pct / Decimal(100))
                t_a = tick_from_price(p_lower, dec0=d0, dec1=d1)
                t_b = tick_from_price(p_upper, dec0=d0, dec1=d1)
                summary_tick_lower = min(t_a, t_b)
                summary_tick_upper = max(t_a, t_b)
        except (TypeError, ValueError, InvalidOperation):
            pass

    in_range_summary = {
        "in_range_steps": in_range_steps,
        "out_of_range_steps": out_of_range_steps,
        "skipped_no_price": skipped_no_price,
        "fraction": in_range_fraction_val,
        "tick_lower": summary_tick_lower,
        "tick_upper": summary_tick_upper,
    }

    # RH-02cn: organic discount summary
    steps_discounted = sum(
        1 for s in steps
        if getattr(s, "organic", None) and s.organic.get("status") == "OK"
    )
    steps_not_discounted = len(steps) - steps_discounted

    fractions = [
        s.organic["fraction"] for s in steps
        if getattr(s, "organic", None) and s.organic.get("status") == "OK" and s.organic.get("fraction") is not None
    ]
    if fractions:
        frac_min = min(fractions)
        frac_max = max(fractions)
        frac_avg = sum(fractions) / Decimal(len(fractions))
    else:
        frac_min = None
        frac_max = None
        frac_avg = None

    accrued_raw = sum(
        (s.organic["fee_usd_raw"] for s in steps
         if getattr(s, "organic", None) and s.organic.get("fee_usd_raw") is not None
         and getattr(s, "in_range", None) is True),
        Decimal(0)
    )
    accrued_organic = sum(
        (s.organic["fee_usd_organic"] for s in steps
         if getattr(s, "organic", None) and s.organic.get("fee_usd_organic") is not None
         and getattr(s, "in_range", None) is True),
        Decimal(0)
    )

    organic_summary = {
        "steps_discounted": steps_discounted,
        "steps_not_discounted": steps_not_discounted,
        "fraction_min": frac_min,
        "fraction_max": frac_max,
        "fraction_avg": frac_avg,
        "accrued_raw": accrued_raw,
        "accrued_organic": accrued_organic,
    }

    return {
        "total_steps": len(steps),
        "eligible_steps": sum(1 for s in steps if s.terminal_eligible),
        "status_counts": status_counts, "dominant_blocker_counts": blocker_counts,
        "size_interval_status_counts": size_interval_status_counts,
        "in_range": in_range_summary,
        "organic": organic_summary,
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
        "conjunct_failure_counts": _conjunct_failure_counts(steps),
        "gas_usd_source": getattr(steps[0], "gas_usd_source", None) if steps else None,
        "gas_reserve": getattr(steps[0], "gas_reserve", None) if steps else None,
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
    p.add_argument("--enforce-gas-reserve", action="store_true", default=False,
                   help="Enforce native gas reserve in terminal gate (default False: record only).")
    p.add_argument("--organic-db", default=DEFAULT_ORGANIC_DB,
                   help="Path to organic.db for volume discount.")
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
                            allow_bare_quote=a.allow_bare_quote,
                            enforce_gas_reserve=a.enforce_gas_reserve,
                            organic_db_path=a.organic_db)
        sc.close()

    payload = {"target_mode": a.target_mode, "pool": a.pool, "strategy_episode": ep,
               "steps": [asdict(s) for s in steps],
               "summary": episode_summary(steps, load_skipped=load_skipped, pool_meta=pool_meta)}
    out_text = json.dumps(payload, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(out_text)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
