#!/usr/bin/env python3
"""RH-04b: single-CORE-pool Shadow runner (orchestration only, read-only).

Wires the six RH layers into one replayable, offline-testable Shadow closed
loop.  Calls existing modules; adds no economic logic.  Live store opened
read-only; all Shadow writes go to a scratch store.  No wallet, no broadcast.
"""
import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
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
    simulated_policy_only: bool
    conjunct_reasons: tuple = ()


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
    # CORE bucket: the on-chain pool price has no independent oracle, so the
    # block timestamp (source_event_time) IS the price's generation time and
    # serves as both oracle_updated_at and api_generated_at.  STOCK buckets
    # must instead go through resolve_freshness (RH-02L); never reuse this.
    flags = evaluate_health(
        oracle_paused=bool(sample.get("oracle_paused")),
        oracle_updated_at=sample.get("source_event_time"),
        api_generated_at=sample.get("source_event_time"),
        now=now_dt,
        halt=bool(sample.get("halt")),
        corp_action_pending=bool(sample.get("corp_action_pending")),
        sources_disagree=bool(sample.get("sources_disagree")),
        chain_degraded=bool(sample.get("chain_degraded")),
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
                capital_usd, target_mode, now_fn, pool_meta=None):
    """Replay one Shadow episode over `samples`, writing gate decisions and position marks to `conn`."""
    steps: list[ShadowStep] = []
    position_open = False
    prev_nav: Optional[Decimal] = None
    prev_fg0: Optional[Decimal] = None
    prev_fg1: Optional[Decimal] = None
    accrued = Decimal(0)
    init0: Optional[Decimal] = None
    init1: Optional[Decimal] = None
    dec0, dec1 = DEFAULT_DEC0, DEFAULT_DEC1
    quote = DEFAULT_QUOTE_USD_PER_TOKEN1

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
        fg0, fg1 = sample.get("fee_growth_global_0"), sample.get("fee_growth_global_1")
        nav: Optional[Decimal] = None
        if fg0 is not None and fg1 is not None:
            cur0, cur1 = Decimal(str(fg0)), Decimal(str(fg1))
            # feeGrowthGlobal is a monotonic cumulative: only the difference
            # between two adjacent readings is the increment.  With no previous
            # reading the increment is "unknown", not "the whole pool's fees":
            # record the reading but leave accrued unchanged (first step adds 0).
            # Explicit `is None` check, not `or Decimal(0)`: Decimal(0) is a
            # legitimate feeGrowth reading (a fresh pool) and `or` would treat
            # it as "no previous value".
            if prev_fg0 is not None and prev_fg1 is not None:
                d0 = cur0 - prev_fg0
                d1 = cur1 - prev_fg1
                accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE
            prev_fg0, prev_fg1 = cur0, cur1
            nav = compute_nav(wallet=capital_usd - position_usd,
                              lp_principal=position_usd, accrued_fees=accrued,
                              verified_rewards=Decimal(0), liabilities=Decimal(0))
        step_net_pnl = (net_pnl(nav, prev_nav, Decimal(0))
                        if nav is not None and prev_nav is not None else None)
        if nav is not None:
            prev_nav = nav

        if init0 is None:
            def _dec(v, d):
                return Decimal(str(v)) if v is not None else d
            init0 = _dec(sample.get("initial_token0_raw"), VIRTUAL_INITIAL_TOKEN0_RAW)
            init1 = _dec(sample.get("initial_token1_raw"), VIRTUAL_INITIAL_TOKEN1_RAW)
            dec0 = int(sample.get("dec0", DEFAULT_DEC0))
            dec1 = int(sample.get("dec1", DEFAULT_DEC1))
            quote = _dec(sample.get("quote_usd_per_token1"), DEFAULT_QUOTE_USD_PER_TOKEN1)
        hodl_value: Optional[Decimal] = None
        if price is not None:
            hodl_value = hodl_benchmark(initial_token0_raw=init0,
                                        initial_token1_raw=init1, dec0=dec0,
                                        dec1=dec1, price_t1_token1_per_token0=price,
                                        quote_usd_per_token1=quote)

        insert_row(conn, "rh_gate_decisions", {
            "decision_id": decision.decision_id, "candidate_key": decision.candidate_key,
            "target_mode": decision.target_mode, "primary_status": decision.primary_status,
            "terminal_bits_json": json.dumps(decision.terminal_bits, sort_keys=True),
            "dominant_blocker": decision.dominant_blocker,
            "reasons_json": json.dumps(decision.reasons, sort_keys=True),
            "snapshot_ids_json": json.dumps(decision.snapshot_ids, sort_keys=True),
            "decided_at": decision.decided_at,
        })
        sample_time = sample.get("sample_time")
        insert_row(conn, "rh_position_marks", {
            "position_id": f"rh-shadow-{strategy_episode}",
            "mark_time": sample_time if sample_time is not None else now_fn(),
            "price_snapshot_id": None, "reference_nav": nav, "liquidation_nav": None,
            "accrued_fee": accrued if nav is not None else None,
            "unvalued_risk_json": json.dumps({"skipped": nav is None}, sort_keys=True),
        })
        steps.append(ShadowStep(
            i, sample_time, price, eligible, decision.primary_status,
            decision.dominant_blocker, nav, step_net_pnl, hodl_value,
            granted, simulated, tuple(step_reasons)))
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
        "FROM rh_market_states WHERE asset_address = ? "
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
        samples.append({
            "asset_address": asset, "sample_time": st, "chain_id": chain_id,
            "reference_mid": Decimal(str(mid)), "multiplier_human": mult,
            # Columns the conjuncts need.  A missing column stays None so the
            # conjunct that needs it fails closed and names itself.
            "session": session,
            "health_flags_json": flags_json,
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
    navs = [s.nav for s in steps if s.nav is not None]
    nav_start = navs[0] if navs else None
    nav_end = navs[-1] if navs else None
    net_pnl_val = (net_pnl(nav_end, nav_start, Decimal(0))
                   if nav_start is not None and nav_end is not None else None)
    hodls = [s.hodl_value for s in steps if s.hodl_value is not None]
    hodl_delta = (hodls[-1] - hodls[0]) if len(hodls) >= 2 else None
    return {
        "total_steps": len(steps),
        "eligible_steps": sum(1 for s in steps if s.terminal_eligible),
        "status_counts": status_counts, "dominant_blocker_counts": blocker_counts,
        "first_eligible_at": next((s.sample_time for s in steps if s.terminal_eligible), None),
        "nav_start": nav_start, "nav_end": nav_end, "net_pnl": net_pnl_val,
        "hodl_delta": hodl_delta,
        # Was one "skipped_samples" field adding these together, which reported
        # 40 when the database held 7 null prices.  They are different facts.
        "skipped_at_load": load_skipped,
        "steps_without_nav": sum(1 for s in steps if s.nav is None),
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
                            now_fn=now, pool_meta=pool_meta)
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
