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
from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID, try_reserve
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


def _candidate_key(sample: Mapping[str, Any], step_index: int) -> str:
    """Per-step unique candidate key so decision_id (PK) never collides."""
    base = (sample.get("candidate_key") or sample.get("pool_key")
            or sample.get("asset_address") or "pool")
    st = sample.get("sample_time")
    return f"{base}@{st}" if st else f"{base}#{step_index}"


def _terminal_record(sample, gated, step_index) -> dict:
    """Merge the gated record with the sample's 9 non-netcover conjuncts + capital_policy_conflict."""
    rec = dict(gated)
    for key in CONJUNCT_ORDER:
        if key != "netcover_pass" and key in sample:
            rec[key] = bool(sample[key])
    if "capital_policy_conflict" in sample:
        rec["capital_policy_conflict"] = sample["capital_policy_conflict"]
    rec["candidate_key"] = _candidate_key(sample, step_index)
    return rec


def run_episode(conn, *, strategy_episode, samples, position_usd, horizon_hours,
                capital_usd, target_mode, now_fn):
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
        record = assemble_rh_clmm_inputs(sample, position_usd=position_usd,
                                         horizon_hours=horizon_hours)
        gated = apply_netcover_gate([record])[0]
        decision = evaluate_terminal_gate(_terminal_record(sample, gated, i),
                                          target_mode=target_mode, now=now_fn())
        eligible = bool(decision.terminal_eligible)
        simulated = bool(decision.simulated_policy_only)

        granted = False
        if eligible and not position_open:
            res = try_reserve(conn, intent_id=f"rh-shadow-{strategy_episode}-{i}",
                              bucket="CORE", amount_usd=position_usd,
                              capital_usd=capital_usd, policy_version=POLICY_ID,
                              now=now_fn())
            granted = bool(res.get("granted"))
            if granted:
                position_open = True

        raw_price = sample.get("reference_mid")
        price = Decimal(str(raw_price)) if raw_price is not None else None
        fg0, fg1 = sample.get("fee_growth_global_0"), sample.get("fee_growth_global_1")
        nav: Optional[Decimal] = None
        if fg0 is not None and fg1 is not None:
            d0 = Decimal(str(fg0)) - (prev_fg0 or Decimal(0))
            d1 = Decimal(str(fg1)) - (prev_fg1 or Decimal(0))
            accrued += position_usd * (d0 + d1) / FEE_GROWTH_SCALE
            prev_fg0, prev_fg1 = Decimal(str(fg0)), Decimal(str(fg1))
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
            granted, simulated))
    return steps


def load_samples_from_db(conn, *, pool: str, limit: int) -> tuple[list[dict], int]:
    """Read real samples for `pool` from rh_market_states in sample_time order; reference_mid IS NULL is skipped and counted (never 0)."""
    cur = conn.execute(
        "SELECT asset_address, sample_time, chain_id, reference_mid, multiplier_human "
        "FROM rh_market_states WHERE asset_address = ? ORDER BY sample_time LIMIT ?",
        (pool, limit))
    samples: list[dict] = []
    skipped = 0
    for asset, st, chain_id, mid, mult in cur.fetchall():
        if mid is None:
            skipped += 1
            continue
        samples.append({
            "asset_address": asset, "sample_time": st, "chain_id": chain_id,
            "reference_mid": Decimal(str(mid)), "multiplier_human": mult,
        })
    return samples, skipped


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
        "skipped_samples": sum(1 for s in steps if s.nav is None) + load_skipped,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RH-04b Shadow runner (read-only).")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--target-mode", default="SHADOW_SCENARIO",
                   choices=["SHADOW_SCENARIO", "LIVE_READINESS"])
    p.add_argument("--pool", default=DEFAULT_POOL)
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    live_conn = open_store(Path(a.db), read_only=True)
    try:
        samples, load_skipped = load_samples_from_db(live_conn, pool=a.pool, limit=a.samples)
    finally:
        live_conn.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        sc = open_store(Path(tmpdir) / "scratch.db", read_only=False)
        migrate(sc)
        now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        ep = "rh-shadow-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        steps = run_episode(sc, strategy_episode=ep, samples=samples,
                            position_usd=Decimal("1000"), horizon_hours=24.0,
                            capital_usd=Decimal("10000"), target_mode=a.target_mode, now_fn=now)
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
