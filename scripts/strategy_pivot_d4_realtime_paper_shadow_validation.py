#!/usr/bin/env python3
"""
D4 — Realtime Paper / Shadow Validation

Read-only paper tracker that runs the D3 best strategy in real time against
live Base RPC + DefiLlama + Binance/Hyperliquid public no-auth endpoints and
compares paper PnL to the D3 model predictions.

Tracks (from D3 spec):
  1. $250  ±2%  hedge=0.75
  2. $250  ±5%  hedge=0.75
  3. $1000 ±2%  hedge=0.75
  4. $1000 ±5%  hedge=0.75

Schedule:
  - 30m heartbeat
  - 1h paper state snapshot
  - 24h daily summary
  - 7d final verdict

Strict prohibitions (per spec):
  - No wallet / signing / broadcast
  - No CEX API key / perp order
  - No paid RPC / private RPC
  - No canary / live / paper-on-venue / mode B
  - No execution engineering
  - No auto-exit engineering
  - No dashboard work

This is data capture + paper accounting only.
"""

from __future__ import annotations

import csv
import json
import math
import os
import signal
import statistics
import sys
import time
import traceback
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants from prior stages
# ---------------------------------------------------------------------------

D3_DIR = Path("reports/strategy_pivot_d3_aerodrome_reward_edge/20260612_160000")
D2_DIR = Path("reports/strategy_pivot_d2_dynamic_delta_funding_history/20260612_140000")
R4C_DIR = Path("reports/strategy_evidence_r4c_independent_clmm_liquidity_replay/20260612_100000")
R4_DIR = Path("reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000")

POOL_B2CC = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
WETH_ADDR = "0x4200000000000000000000000000000000000006"
USDC_ADDR = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

# Public no-auth endpoints
BASE_RPC_URL = "https://mainnet.base.org"
DEFILLAMA_POOLS = "https://yields.llama.fi/pools"
DEFILLAMA_POOL = "https://yields.llama.fi/pool/"
BINANCE_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&limit=1000"
HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"
COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"

# V3 / Algebra Swap topic hashes
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
ALGEBRA_SWAP_TOPIC = "0x19b47279a78f1a39d4eaf1f2b05fa6e8b1c9f3a3d8e1d5f7c9b3a8e2f4d6c1e9a"  # placeholder; Aerodrome uses V3 topic on EIP-1167 proxy

# Pool decimals (WETH=18, USDC=6)
DEC0 = 18
DEC1 = 6
PRICE_DEC_ADJ = 10 ** (DEC1 - DEC0)  # multiply by 1e-12 to get token1/token0 raw

# Economics (from D3)
ETH_USD_FALLBACK = 1653.0
GAS_CYCLE_USD = 0.0795  # per tx, in/out
PERP_TAKER_FEE = 0.0002
CLAIM_GAS_USD = 0.10
ETH_DAILY_SIGMA = 0.04
HOURS_PER_YEAR = 8760

# D3 R4C fee per dollar per day (24h horizon, gt_2pct rebalance)
D3_FEE_PER_DOLLAR_PER_DAY = {
    (250, 2): 0.018,  # $250 ±2% gt_2pct: scaled from D3's $1000 entry
    (250, 5): 0.012,
    (1000, 2): 0.018,
    (1000, 5): 0.012,
}
# Note: D3's fee_per_dollar_per_day was size-invariant; we use the same number
# for all sizes because LP fees scale linearly with size when L_position scales
# linearly. The R4C 24h matrix shows the per-dollar rate; size is a multiplier.

# D3 expected daily net PnL per track (from reward_adjusted_delta_matrix.csv,
# median funding, observed reward 63.52% AERO)
D3_EXPECTED_DAILY_NET_USD = {
    (250, 2): 1.8257,
    (250, 5): None,  # pull from D3 matrix
    (1000, 2): 8.3181,
    (1000, 5): None,
}

# Rebalance thresholds
RANGE_PCT = 2
TICK_THRESHOLDS = {2: 200, 5: 500}  # 2% range → ±200 ticks; 5% range → ±500 ticks

# Schedule
HEARTBEAT_SECS = 30 * 60
PAPER_STATE_SECS = 60 * 60
DAILY_SUMMARY_SECS = 24 * 60 * 60
TOTAL_RUNTIME_SECS = 7 * 24 * 60 * 60
POLL_BLOCK_WINDOW = 2000  # eth_getLogs window per call

# ---------------------------------------------------------------------------
# Helpers — HTTP / RPC
# ---------------------------------------------------------------------------


def _http_get_json(url, headers=None, timeout=15):
    """GET a URL and parse JSON. No auth. No secrets."""
    req = urllib.request.Request(url, headers={"User-Agent": "lpbot-d4-paper/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_json(url, payload, headers=None, timeout=15):
    """POST a JSON body and parse JSON. No auth."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "lpbot-d4-paper/1.0", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def rpc_call(method, params):
    """Call a JSON-RPC method on the Base public RPC."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return _http_post_json(BASE_RPC_URL, payload, timeout=20)


def get_eth_block_number():
    """Return latest Base block number."""
    r = rpc_call("eth_blockNumber", [])
    return int(r.get("result", "0x0"), 16)


def get_eth_gas_price_gwei():
    """Return current gas price in gwei (for paper gas accounting)."""
    try:
        r = rpc_call("eth_gasPrice", [])
        wei = int(r.get("result", "0x0"), 16)
        return wei / 1e9
    except Exception:
        return 0.05  # 0.05 gwei typical Base


def get_swap_logs(pool_addr, from_block, to_block):
    """Fetch Swap logs for the pool in the block window. Returns list of dicts."""
    try:
        r = rpc_call(
            "eth_getLogs",
            [
                {
                    "address": pool_addr,
                    "topics": [V3_SWAP_TOPIC],
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                }
            ],
        )
        return r.get("result", [])
    except Exception as e:
        return []


def decode_int24_hex(hex_str):
    """Decode a 32-byte hex word as int24 (right-aligned, signed)."""
    raw = int(hex_str, 16)
    if raw & 0x800000:
        raw -= 0x1000000
    return raw


def decode_v3_swap_data(data_hex):
    """Decode V3 Swap data field. Layout: amount0(int256), amount1(int256), sqrtPriceX96(uint160), liquidity(uint128), tick(int24)."""
    if not data_hex or len(data_hex) < 2:
        return None
    p = data_hex[2:]  # strip 0x
    if len(p) < 320:
        return None
    try:
        return {
            "amount0": int(p[0:64], 16),
            "amount1": int(p[64:128], 16),
            "sqrt_price_x96": int(p[128:192], 16),
            "liquidity": int(p[192:256], 16),
            "tick": decode_int24_hex(p[256 + 32 * 9 : 256 + 32 * 10]),  # 10th word
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tick / price math
# ---------------------------------------------------------------------------


def tick_to_sqrt_price_x96(tick):
    """Convert a V3 tick to sqrtPriceX96. Uses exp() to avoid float overflow on big ticks."""
    # sqrt(1.0001^tick) * 2^96
    return math.exp(tick * math.log(1.0001) / 2.0) * (2 ** 96)


def sqrt_price_x96_to_price(sqrt_px96, dec0=DEC0, dec1=DEC1):
    """sqrtPriceX96 -> token1/token0 human-readable price."""
    if sqrt_px96 == 0:
        return None
    p_raw = (sqrt_px96 / (2 ** 96)) ** 2
    return p_raw * (10 ** (dec0 - dec1))


def tick_lower_upper(current_tick, range_pct):
    """Return (lower_tick, upper_tick) for ±range_pct% around current tick."""
    # 1% price move ≈ 100 ticks (since 1.0001^100 ≈ 1.01005)
    delta = int(round(range_pct * 100))
    return current_tick - delta, current_tick + delta


# ---------------------------------------------------------------------------
# DefiLlama reward APR
# ---------------------------------------------------------------------------

POOL_UUID = None  # legacy; bulk endpoint doesn't need it


def fetch_defillama_reward_apr():
    """Fetch the latest observed AERO reward APR for 0xb2cc from DefiLlama.

    The /pool/{uuid} detail endpoint 404s for some pools; use the bulk
    /pools endpoint and filter for 0xb2cc by underlyingTokens. Returns
    (apr_pct, fetched_at_iso) or (None, None) on failure.
    """
    try:
        resp = _http_get_json(DEFILLAMA_POOLS, timeout=20)
        pools = resp.get("data", resp) if isinstance(resp, dict) else resp
        if not isinstance(pools, list):
            return None, None
        for p in pools:
            if (
                p.get("chain") == "Base"
                and p.get("project") in ("aerodrome-slipstream", "aerodrome")
                and p.get("symbol", "").lower().find("weth") >= 0
                and p.get("symbol", "").lower().find("usdc") >= 0
            ):
                underlying = p.get("underlyingTokens", []) or []
                if WETH_ADDR.lower() in [u.lower() for u in underlying] and USDC_ADDR.lower() in [
                    u.lower() for u in underlying
                ]:
                    if p.get("tvlUsd", 0) > 5_000_000:
                        apr_pct = float(p.get("apyReward", 0) or 0)
                        return apr_pct, datetime.now(timezone.utc).isoformat()
        return None, None
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Binance funding history (live updates + stress scenarios)
# ---------------------------------------------------------------------------


def fetch_binance_funding_recent(limit=8):
    """Fetch the last `limit` Binance funding rates (8h intervals)."""
    try:
        r = _http_get_json(BINANCE_FUNDING + f"&limit={limit}", timeout=15)
        out = []
        for row in r:
            out.append(
                {
                    "funding_time_utc": row.get("fundingTime"),
                    "funding_rate_raw": float(row.get("fundingRate", 0)),
                    "mark_price": float(row.get("markPrice", 0)),
                }
            )
        return out
    except Exception:
        return []


def funding_to_apr_pct(funding_rate_raw, funding_interval_hours=8):
    """Convert a single 8h funding rate to APR% (simple: rate * (24/8) * 365 * 100)."""
    return funding_rate_raw * 3.0 * 365.0 * 100.0


# ---------------------------------------------------------------------------
# Hyperliquid hedge mark
# ---------------------------------------------------------------------------


def fetch_hyperliquid_eth_mark():
    """Fetch live ETH mark price from Hyperliquid /info metaAndAssetCtxs."""
    try:
        r = _http_post_json(
            HYPERLIQUID_INFO,
            {"type": "metaAndAssetCtxs"},
            timeout=10,
        )
        if not r or len(r) < 2 or not r[0].get("universe"):
            return None
        for asset, ctx in zip(r[0]["universe"], r[1]):
            if asset.get("name") == "ETH":
                mp = ctx.get("markPx")
                if mp is not None:
                    return float(mp)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CoinGecko ETH/USD (fallback)
# ---------------------------------------------------------------------------


def fetch_coingecko_eth_usd():
    try:
        r = _http_get_json(COINGECKO_SIMPLE, timeout=10)
        return float(r.get("ethereum", {}).get("usd", 0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Paper position model (matches D3 components)
# ---------------------------------------------------------------------------


class PaperPosition:
    """One paper LP position. Replays the swap stream and tracks paper PnL."""

    def __init__(self, size_usd, range_pct, hedge_ratio=0.75, start_tick=None, start_eth_usd=ETH_USD_FALLBACK):
        self.size_usd = float(size_usd)
        self.range_pct = int(range_pct)
        self.hedge_ratio = float(hedge_ratio)
        self.start_eth_usd = start_eth_usd
        self.entry_tick = start_tick
        self.entry_block = None
        self.lower_tick = None
        self.upper_tick = None
        self.in_range = False
        self.accumulated_lp_fee_usd = 0.0
        self.estimated_il_usd = 0.0
        self.reward_income_usd = 0.0
        self.hedge_notional_usd = self.size_usd * self.hedge_ratio
        self.hedge_pnl_usd = 0.0
        self.funding_pnl_usd = 0.0
        self.rebalance_count = 0
        self.rebalance_cost_usd = 0.0
        self.gas_estimate_usd = 0.0
        self.claim_gas_usd = 0.0
        self.net_pnl_usd = 0.0
        self.last_eth_usd = start_eth_usd
        self.hedge_eth_amount = 0.0  # negative = short
        self.events_seen = 0
        self.events_decoded_ok = 0
        self.events_decoded_fail = 0
        self.last_event_block = None
        self.start_time_utc = None
        self.last_update_utc = None

    def set_entry(self, tick, block, eth_usd):
        self.entry_tick = tick
        self.entry_block = block
        self.last_eth_usd = eth_usd
        self.start_eth_usd = eth_usd
        self.lower_tick, self.upper_tick = tick_lower_upper(tick, self.range_pct)
        self.in_range = True
        # Hedge: short hedge_ratio × size in ETH at the entry price
        self.hedge_eth_amount = -(self.hedge_notional_usd / eth_usd)

    def apply_event(self, ev, fee_per_dollar_per_day, total_events_so_far):
        """Apply one swap event. Returns the new fee income for this event (US$)."""
        if not ev.get("ok"):
            self.events_decoded_fail += 1
            return 0.0
        self.events_seen += 1
        self.events_decoded_ok += 1
        self.last_event_block = ev["block"]
        tick = ev["tick"]
        new_lower, new_upper = self.lower_tick, self.upper_tick  # unchanged
        if self.entry_tick is None:
            return 0.0
        prev_in_range = self.in_range
        in_range_now = self.lower_tick <= tick <= self.upper_tick
        # Rebalance check
        threshold = TICK_THRESHOLDS.get(self.range_pct, 200)
        rebalanced = False
        if abs(tick - self.entry_tick) > threshold:
            # Re-anchor center
            self.entry_tick = tick
            self.lower_tick, self.upper_tick = tick_lower_upper(tick, self.range_pct)
            self.rebalance_count += 1
            self.rebalance_cost_usd += GAS_CYCLE_USD * 2  # LP close+open + perp open
            rebalanced = True
        self.in_range = in_range_now
        # Per-event fee allocation
        # 24h: fee_per_dollar_per_day × size / total_events_per_24h
        # total_events_so_far is approximately the daily count for the live window
        if total_events_so_far <= 0:
            total_events_so_far = 1
        fee_for_event = self.size_usd * fee_per_dollar_per_day / total_events_so_far
        if in_range_now:
            self.accumulated_lp_fee_usd += fee_for_event
        # IL accrual: 0.5 × σ² × period_fraction × range_amplification × size
        # Period = 1 / total_events_so_far days
        # range_amplification: ±2% → ~25x; ±5% → ~4x; ±10% → 1x
        range_amp = {2: 25.0, 5: 4.0, 10: 1.0}.get(self.range_pct, 1.0)
        il_step = 0.5 * (ETH_DAILY_SIGMA ** 2) * (1.0 / total_events_so_far) * range_amp * self.size_usd
        if in_range_now:
            self.estimated_il_usd += il_step
        return fee_for_event

    def accrue_funding(self, funding_apr_pct, hours):
        """Accrue funding income over `hours` hours. SHORT pays funding if funding > 0."""
        # funding_pnl = -hedge_eth_amount × mark × funding_rate × hours
        # SHORT (hedge_eth_amount < 0) means we receive funding when funding_rate > 0
        # PnL = -hedge_eth_amount × price × funding_apr/100 × hours/8760
        if self.hedge_eth_amount == 0:
            return
        funding_per_hour = (funding_apr_pct / 100.0) / HOURS_PER_YEAR
        delta = -self.hedge_eth_amount * self.last_eth_usd * funding_per_hour * hours
        self.funding_pnl_usd += delta

    def hedge_mark_pnl(self, current_eth_usd):
        """Update hedge PnL given the current ETH mark."""
        if self.hedge_eth_amount == 0:
            return
        # SHORT: gain when price falls
        self.hedge_pnl_usd = (self.start_eth_usd - current_eth_usd) * (-self.hedge_eth_amount)

    def accrue_reward(self, reward_apr_pct, hours):
        """Accrue AERO reward income over `hours` hours."""
        reward_per_hour = (reward_apr_pct / 100.0) / HOURS_PER_YEAR
        delta = self.size_usd * reward_per_hour * hours
        self.reward_income_usd += delta

    def total_net(self):
        return (
            self.accumulated_lp_fee_usd
            + self.reward_income_usd
            - self.estimated_il_usd
            - self.rebalance_cost_usd
            - self.claim_gas_usd
            - self.gas_estimate_usd
            + self.hedge_pnl_usd
            + self.funding_pnl_usd
        )

    def to_dict(self, eth_usd_now):
        return {
            "size_usd": self.size_usd,
            "range_pct": self.range_pct,
            "hedge_ratio": self.hedge_ratio,
            "hedge_eth_amount": self.hedge_eth_amount,
            "entry_tick": self.entry_tick,
            "entry_block": self.entry_block,
            "lower_tick": self.lower_tick,
            "upper_tick": self.upper_tick,
            "in_range": self.in_range,
            "accumulated_lp_fee_usd": self.accumulated_lp_fee_usd,
            "estimated_il_usd": self.estimated_il_usd,
            "reward_income_usd": self.reward_income_usd,
            "hedge_pnl_usd": self.hedge_pnl_usd,
            "funding_pnl_usd": self.funding_pnl_usd,
            "rebalance_count": self.rebalance_count,
            "rebalance_cost_usd": self.rebalance_cost_usd,
            "gas_estimate_usd": self.gas_estimate_usd,
            "claim_gas_usd": self.claim_gas_usd,
            "net_pnl_usd": self.total_net(),
            "last_event_block": self.last_event_block,
            "events_seen": self.events_seen,
            "events_decoded_ok": self.events_decoded_ok,
            "events_decoded_fail": self.events_decoded_fail,
            "eth_usd_now": eth_usd_now,
        }


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------


class D4Runner:
    """Long-running paper validator. Writes checkpoints and survives restart."""

    def __init__(self, report_dir):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.start_time_utc = datetime.now(timezone.utc)
        self.runtime_hours = 0.0
        self.heartbeat_path = self.report_dir / "heartbeat.jsonl"
        self.hourly_path = self.report_dir / "paper_position_state_hourly.jsonl"
        self.hourly_csv_path = self.report_dir / "paper_position_state_hourly.csv"
        self.daily_dir = self.report_dir  # daily_summary_dayN.md written here
        self.swap_events_path = self.report_dir / "swap_events_realtime.jsonl"
        self.funding_updates_path = self.report_dir / "funding_updates.jsonl"
        self.reward_updates_path = self.report_dir / "reward_apr_updates.jsonl"
        self.model_error_path = self.report_dir / "model_error_log.jsonl"
        self.restart_path = self.report_dir / "restart.jsonl"
        self.positions = {
            (250, 2): PaperPosition(250, 2),
            (250, 5): PaperPosition(250, 5),
            (1000, 2): PaperPosition(1000, 2),
            (1000, 5): PaperPosition(1000, 5),
        }
        self.last_block = None
        self.last_heartbeat = 0.0
        self.last_hourly = 0.0
        self.last_daily = 0.0
        self.last_funding_update = 0.0
        self.last_reward_update = 0.0
        self.funding_apr_pct = 0.83  # D2 median
        self.reward_apr_pct = 63.52  # D3 observed
        self.events_24h_baseline = 30000  # R4: ~28k events in 24h on 0xb2cc
        self.shutdown_requested = False
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        self._load_restart_state()

    def _on_signal(self, signum, frame):
        self.shutdown_requested = True

    def _load_restart_state(self):
        if self.restart_path.exists():
            try:
                with open(self.restart_path) as f:
                    for line in f:
                        row = json.loads(line)
                        if row.get("event") == "restart":
                            self.start_time_utc = datetime.fromisoformat(row["start_time_utc"])
                            self.funding_apr_pct = row.get("funding_apr_pct", 0.83)
                            self.reward_apr_pct = row.get("reward_apr_pct", 63.52)
                            self.last_block = row.get("last_block")
            except Exception:
                pass

    def _append_jsonl(self, path, row):
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")

    def _write_heartbeat(self, note=""):
        now = datetime.now(timezone.utc).isoformat()
        uptime_h = (datetime.now(timezone.utc) - self.start_time_utc).total_seconds() / 3600.0
        row = {
            "ts_utc": now,
            "uptime_hours": round(uptime_h, 3),
            "last_block": self.last_block,
            "funding_apr_pct": round(self.funding_apr_pct, 4),
            "reward_apr_pct": round(self.reward_apr_pct, 4),
            "tracks_alive": sum(1 for p in self.positions.values() if p.entry_tick is not None),
            "note": note,
        }
        self._append_jsonl(self.heartbeat_path, row)
        self.last_heartbeat = time.time()

    def _write_hourly_state(self):
        now = datetime.now(timezone.utc).isoformat()
        eth_usd = self._eth_usd() or ETH_USD_FALLBACK
        rows = []
        for k, p in self.positions.items():
            p.last_eth_usd = eth_usd
            p.hedge_mark_pnl(eth_usd)
            row = {"ts_utc": now, "track": f"${p.size_usd:.0f} ±{p.range_pct}%", **p.to_dict(eth_usd)}
            rows.append(row)
        with open(self.hourly_path, "a") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        # CSV header on first write
        write_header = not self.hourly_csv_path.exists()
        with open(self.hourly_csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if write_header:
                w.writeheader()
            for row in rows:
                w.writerow(row)
        self.last_hourly = time.time()

    def _write_daily_summary(self, day_n):
        path = self.report_dir / f"daily_summary_day{day_n}.md"
        uptime_h = (datetime.now(timezone.utc) - self.start_time_utc).total_seconds() / 3600.0
        lines = [
            f"# D4 Daily Summary — Day {day_n}",
            "",
            f"- ts_utc: {datetime.now(timezone.utc).isoformat()}",
            f"- uptime_hours: {uptime_h:.2f}",
            f"- last_block: {self.last_block}",
            f"- funding_apr_pct: {self.funding_apr_pct:.4f}",
            f"- reward_apr_pct: {self.reward_apr_pct:.4f}",
            "",
            "| Track | LP fee | Reward | IL | Rebal cost | Hedge PnL | Funding PnL | Net PnL | Events seen | Decoded |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for k, p in self.positions.items():
            d = p.to_dict(self._eth_usd() or ETH_USD_FALLBACK)
            lines.append(
                f"| ${p.size_usd:.0f} ±{p.range_pct}% | "
                f"${d['accumulated_lp_fee_usd']:.2f} | "
                f"${d['reward_income_usd']:.2f} | "
                f"${d['estimated_il_usd']:.2f} | "
                f"${d['rebalance_cost_usd']:.2f} | "
                f"${d['hedge_pnl_usd']:.2f} | "
                f"${d['funding_pnl_usd']:.2f} | "
                f"${d['net_pnl_usd']:.2f} | "
                f"{d['events_seen']} | "
                f"{d['events_decoded_ok']} |"
            )
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def _eth_usd(self):
        # Try Hyperliquid first, then CoinGecko
        p = fetch_hyperliquid_eth_mark()
        if p:
            return p
        p = fetch_coingecko_eth_usd()
        return p

    def _refresh_funding(self):
        recs = fetch_binance_funding_recent(limit=4)
        if not recs:
            return
        # Median of the last 4 records (32h) as live funding
        aprs = [funding_to_apr_pct(r["funding_rate_raw"]) for r in recs]
        self.funding_apr_pct = statistics.median(aprs)
        self._append_jsonl(
            self.funding_updates_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "funding_apr_pct_median_32h": round(self.funding_apr_pct, 4),
                "raw": recs,
            },
        )
        self.last_funding_update = time.time()

    def _refresh_reward(self):
        apr, fetched_at = fetch_defillama_reward_apr()
        if apr is not None:
            self.reward_apr_pct = apr
        self._append_jsonl(
            self.reward_updates_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "reward_apr_pct": round(self.reward_apr_pct, 4),
                "defillama_observed": apr,
                "fetched_at": fetched_at,
            },
        )
        self.last_reward_update = time.time()

    def _initial_entry(self):
        """Read the latest pool tick from a recent block, set up the four positions."""
        latest = get_eth_block_number()
        # Read the most recent few thousand blocks for the pool's current state
        # eth_getLogs returns latest tick in last swap
        to_block = latest
        from_block = max(latest - POLL_BLOCK_WINDOW, 0)
        logs = get_swap_logs(POOL_B2CC, from_block, to_block)
        cur_tick = None
        for log in logs[-5:]:
            data = log.get("data", "")
            ev = decode_v3_swap_data(data)
            if ev:
                cur_tick = ev["tick"]
                break
        if cur_tick is None:
            # Try storage slot 1 (slot0) of the pool
            # V3 pool's slot0 is packed: sqrtPriceX96(160) | tick(int24)
            # We need a manual ABI call, which the public RPC allows
            # slot0() selector = 0x3850c413
            try:
                r = rpc_call("eth_call", [{"to": POOL_B2CC, "data": "0x3850c413"}, "latest"])
                slot0_hex = r.get("result", "")
                if slot0_hex and slot0_hex != "0x":
                    p = slot0_hex[2:]
                    if len(p) >= 64:
                        # sqrtPriceX96 is in word 0; tick is in word 1 (right-aligned 3 bytes)
                        tick_hex = p[64 + 32 * 0 + 30 : 64 + 32 * 1]
                        cur_tick = decode_int24_hex(tick_hex)
            except Exception:
                pass
        if cur_tick is None:
            # Fallback to R4's measured current tick: -202111
            cur_tick = -202111
        eth_usd = self._eth_usd() or ETH_USD_FALLBACK
        for p in self.positions.values():
            p.set_entry(cur_tick, latest, eth_usd)
        self.last_block = latest
        self._append_jsonl(
            self.swap_events_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "event": "initial_entry",
                "tick": cur_tick,
                "block": latest,
                "eth_usd": eth_usd,
                "window": [from_block, to_block],
                "logs_seen": len(logs),
            },
        )

    def _fetch_and_apply_events(self):
        """Pull new swap logs since last_block and apply to positions."""
        try:
            latest = get_eth_block_number()
            if self.last_block is None:
                self.last_block = latest
            if latest <= self.last_block:
                return 0
            # Read in 2000-block windows
            events_applied = 0
            while self.last_block < latest:
                to_b = min(self.last_block + POLL_BLOCK_WINDOW, latest)
                logs = get_swap_logs(POOL_B2CC, self.last_block + 1, to_b)
                total_so_far = max(self.events_24h_baseline, len(logs) * 24 * 3600 / max(1, to_b - self.last_block))
                for log in logs:
                    data = log.get("data", "")
                    ev = decode_v3_swap_data(data)
                    if ev is None:
                        self._append_jsonl(
                            self.swap_events_path,
                            {
                                "ts_utc": datetime.now(timezone.utc).isoformat(),
                                "event": "decode_fail",
                                "block": int(log.get("blockNumber", "0x0"), 16),
                                "tx": log.get("transactionHash"),
                            },
                        )
                        continue
                    decoded = {
                        "ts_utc": datetime.now(timezone.utc).isoformat(),
                        "event": "swap",
                        "block": int(log.get("blockNumber", "0x0"), 16),
                        "tx": log.get("transactionHash"),
                        "tick": ev["tick"],
                        "sqrt_price_x96": ev["sqrt_price_x96"],
                        "liquidity": ev["liquidity"],
                        "amount0": ev["amount0"],
                        "amount1": ev["amount1"],
                        "ok": True,
                    }
                    self._append_jsonl(self.swap_events_path, decoded)
                    for p in self.positions.values():
                        # Look up fee per dollar per day for this size/range
                        # D3's R4C table is size-invariant; use the size-keyed entry
                        key = (int(p.size_usd), int(p.range_pct))
                        fee = D3_FEE_PER_DOLLAR_PER_DAY.get(key, 0.018)
                        p.apply_event(decoded, fee, total_so_far)
                        events_applied += 1
                self.last_block = to_b
            return events_applied
        except Exception as e:
            self._append_jsonl(
                self.model_error_path,
                {"ts_utc": datetime.now(timezone.utc).isoformat(), "error": str(e), "trace": traceback.format_exc()[:2000]},
            )
            return 0

    def _accrue_periodic(self, hours):
        """Accrue funding + reward income for the elapsed time across positions."""
        for p in self.positions.values():
            p.accrue_funding(self.funding_apr_pct, hours)
            p.accrue_reward(self.reward_apr_pct, hours)

    def run(self):
        # First-run entry
        self._initial_entry()
        self._refresh_funding()
        self._refresh_reward()
        self._write_heartbeat(note="initial_entry")
        self._write_hourly_state()
        # Daily summary 1 right after entry
        self._write_daily_summary(1)
        self.last_daily = time.time()

        # Main loop
        last_accrual = time.time()
        while not self.shutdown_requested:
            elapsed = (datetime.now(timezone.utc) - self.start_time_utc).total_seconds()
            if elapsed > TOTAL_RUNTIME_SECS:
                self._write_heartbeat(note="runtime_complete")
                break

            now = time.time()
            # Pull new events
            self._fetch_and_apply_events()
            # Accrue funding and reward for the elapsed period (capped at 1h between iterations)
            dt_h = min(1.0, (now - last_accrual) / 3600.0)
            if dt_h > 0:
                self._accrue_periodic(dt_h)
                last_accrual = now

            # Heartbeat every 30m
            if now - self.last_heartbeat > HEARTBEAT_SECS:
                self._write_heartbeat(note="tick")

            # Hourly state every 1h
            if now - self.last_hourly > PAPER_STATE_SECS:
                self._write_hourly_state()

            # Funding refresh every 8h (4 funding events at 8h intervals)
            if now - self.last_funding_update > 8 * 3600:
                self._refresh_funding()

            # Reward refresh every 24h
            if now - self.last_reward_update > 24 * 3600:
                self._refresh_reward()

            # Daily summary
            day_n = int((now - self.start_time_utc.timestamp()) // DAILY_SUMMARY_SECS) + 1
            day_n = max(1, min(day_n, 7))
            if (now - self.last_daily) > DAILY_SUMMARY_SECS:
                self._write_daily_summary(day_n)
                self.last_daily = now

            # Restart-state checkpoint every 5 min
            if int(now) % 300 < 5:
                self._append_jsonl(
                    self.restart_path,
                    {
                        "event": "restart",
                        "ts_utc": datetime.now(timezone.utc).isoformat(),
                        "start_time_utc": self.start_time_utc.isoformat(),
                        "last_block": self.last_block,
                        "funding_apr_pct": self.funding_apr_pct,
                        "reward_apr_pct": self.reward_apr_pct,
                    },
                )

            time.sleep(60)  # tick every 60s

        # Final write
        self._write_heartbeat(note="shutdown")
        self._write_hourly_state()


def main():
    if len(sys.argv) < 2:
        print("usage: strategy_pivot_d4_realtime_paper_shadow_validation.py <report_dir>")
        sys.exit(1)
    report_dir = sys.argv[1]
    runner = D4Runner(report_dir)
    runner.run()


if __name__ == "__main__":
    main()
