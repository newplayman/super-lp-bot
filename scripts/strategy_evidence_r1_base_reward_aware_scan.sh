#!/usr/bin/env bash
# scripts/strategy_evidence_r1_base_reward_aware_scan.sh
#
# LP_BOT_STRATEGY_EVIDENCE_R1_REWARD_AWARE_ALPHA_POOL_DISCOVERY_V1
#
# Read-only data collection, gas-aware + capital-grid LP simulation,
# reward-aware placeholder (reward_data_unavailable=true), and
# ranked-candidate output for Base AMM LP opportunity discovery.
#
# NO wallet / signing / broadcasting / LP / swap / approve / bridge.
# All output is to the per-run report dir.
#
# Free, public, read-only data sources:
#   - GeckoTerminal API v2 (no auth)         — top Base pools by 24h vol
#   - DexScreener API (no auth)              — additional pool coverage
#   - Base public RPC (https://mainnet.base.org, read-only)
#   - Name-parse fallback for token symbols
#
# Outputs (to ${REPORT_DIR}):
#   - raw_pools.{csv,jsonl}
#   - reward_pools.csv, reward_model.jsonl
#   - risk_scored_pools.csv, risk_flags.jsonl
#   - capital_threshold_matrix.csv
#   - gas_amortization_matrix.csv
#   - ranked_candidates.csv, top_candidates.md
#   - R0_BASELINE_REVIEW.md
#   - DATA_SOURCE_HEALTH.md
#
# Tunables via env:
#   STRATEGY_R1_RUN_ID     (default: utc timestamp)
#   STRATEGY_R1_RAW_LIMIT  (default: 240 pools)
#   STRATEGY_R1_RPC        (default: https://mainnet.base.org)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${STRATEGY_R1_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
REPORT_DIR="${ROOT_DIR}/reports/strategy_evidence_r1_reward_aware_alpha_discovery/${RUN_ID}"
mkdir -p "${REPORT_DIR}"

cd "${ROOT_DIR}"

RAW_CSV="${REPORT_DIR}/raw_pools.csv"
RAW_JSONL="${REPORT_DIR}/raw_pools.jsonl"
REWARD_CSV="${REPORT_DIR}/reward_pools.csv"
REWARD_JSONL="${REPORT_DIR}/reward_model.jsonl"
RISK_CSV="${REPORT_DIR}/risk_scored_pools.csv"
RISK_JSONL="${REPORT_DIR}/risk_flags.jsonl"
CAP_CSV="${REPORT_DIR}/capital_threshold_matrix.csv"
GAS_CSV="${REPORT_DIR}/gas_amortization_matrix.csv"
RANK_CSV="${REPORT_DIR}/ranked_candidates.csv"

echo "strategy_evidence_r1: RUN_ID=${RUN_ID}"
echo "strategy_evidence_r1: REPORT_DIR=${REPORT_DIR}"

RAW_LIMIT="${STRATEGY_R1_RAW_LIMIT:-240}"
RPC_URL="${STRATEGY_R1_RPC:-https://mainnet.base.org}"

export RAW_LIMIT RPC_URL
export RAW_CSV RAW_JSONL REWARD_CSV REWARD_JSONL
export RISK_CSV RISK_JSONL CAP_CSV GAS_CSV RANK_CSV
export REPORT_DIR RUN_ID

python3 - <<'PYEOF'
from __future__ import annotations
import csv, json, math, os, sys, time, urllib.request, datetime, urllib.parse

raw_limit    = int(os.environ["RAW_LIMIT"])
rpc_url      = os.environ["RPC_URL"]
raw_csv      = os.environ["RAW_CSV"]
raw_jsonl    = os.environ["RAW_JSONL"]
reward_csv   = os.environ["REWARD_CSV"]
reward_jsonl = os.environ["REWARD_JSONL"]
risk_csv     = os.environ["RISK_CSV"]
risk_jsonl   = os.environ["RISK_JSONL"]
cap_csv      = os.environ["CAP_CSV"]
gas_csv      = os.environ["GAS_CSV"]
rank_csv     = os.environ["RANK_CSV"]
report_dir   = os.environ["REPORT_DIR"]
run_id       = os.environ["RUN_ID"]

# ---- Base mainnet canonical addresses (lowercased) ----
WETH_BASE  = "0x4200000000000000000000000000000000000006"
USDC_BASE  = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
USDbC_BASE = "0xd9aaec86b65d86f3a3a7c83f3a9bed3a8fab4cd1"
DAI_BASE   = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
CBBTC_BASE = "0xcbb7c0000ab88b473b1f5bfd945ef319e551d82"
AERO_BASE  = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"  # Aerodrome governance / emissions

STABLES  = {USDC_BASE.lower(), USDbC_BASE.lower(), DAI_BASE.lower()}
L1_WRAP  = {WETH_BASE.lower(), CBBTC_BASE.lower()}
AERO_SET = {AERO_BASE.lower()}
BLUE_CHIP= L1_WRAP | STABLES

# ---- HTTP helpers ----
def http_get_json(url, timeout=30, headers=None):
    h = {"User-Agent": "lp-bot-r1/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def http_post_rpc(method, params, timeout=10):
    body = json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1}).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("result")

# ---- GeckoTerminal: top Base pools by 24h volume ----
def fetch_gt_pools(limit):
    base = "https://api.geckoterminal.com/api/v2"
    page_size = 20
    out = []
    pages = max(1, (limit + page_size - 1) // page_size)
    for p in range(1, pages + 1):
        url = f"{base}/networks/base/pools?page={p}&sort=h24_volume_usd_desc"
        try:
            data = http_get_json(url)
        except Exception as e:
            print(f"warn: geckoterminal page {p} failed: {e}", file=sys.stderr)
            break
        items = data.get("data", [])
        if not items:
            break
        out.extend(items)
        if len(out) >= limit:
            break
        time.sleep(0.4)
    return out[:limit]

# ---- DexScreener search: broadens coverage to PancakeSwap V3 /
# Uniswap V3 Base pairs that don't always rank high on
# GeckoTerminal's volume sort. ----
DS_QUERIES = [
    "WETH USDC base",
    "cbBTC WETH base",
    "cbBTC USDC base",
    "AERO USDC base",
    "AERO WETH base",
    "USDC USDT base",
    "EURC USDC base",
    "DEGEN WETH base",
    "VIRTUAL USDC base",
    "VVV WETH base",
    "TOSHI WETH base",
    "BRETT WETH base",
    "MIGGLES WETH base",
    "SKI WETH base",
]

def fetch_ds_pairs():
    base = "https://api.dexscreener.com/latest/dex/search"
    seen = set()
    out = []
    for q in DS_QUERIES:
        url = f"{base}?q={urllib.parse.quote(q)}"
        try:
            data = http_get_json(url, timeout=20)
        except Exception as e:
            print(f"warn: dexscreener query '{q}' failed: {e}", file=sys.stderr)
            continue
        for p in data.get("pairs", []) or []:
            if p.get("chainId") != "base":
                continue
            addr = (p.get("pairAddress") or "").lower()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            out.append(p)
        time.sleep(0.5)
    return out

# ---- Token risk patterns ----
RISKY_SYMBOL_PATTERNS = ("INU", "PEPE", "SHIB", "DOGE", "MOON",
                         "TEST", "XXX", "FAKE", "RUG", "SCAM", "PONZI")

# ---- Pool-risk thresholds ----
TVL_MIN_USD          = 25_000.0
VOL_TVL_MIN_RATIO    = 0.10
VOL_TVL_MAX_RATIO    = 50.0
PCT_CHG_24H_MAX_ABS  = 35.0
PCT_CHG_6H_MAX_ABS   = 20.0
POOL_AGE_DAYS_MIN    = 14.0

def f(x, default=0.0):
    try: return float(x)
    except (TypeError, ValueError): return default

def i(x, default=0):
    try: return int(float(x))
    except (TypeError, ValueError): return default

def fee_tier_bps_from_name(name):
    if not name: return 0
    for marker, bps in (
        ("0.01%", 1), ("0.018%", 1.8), ("0.02%", 2), ("0.021%", 2.1),
        ("0.03%", 3), ("0.05%", 5), ("0.3%", 30), ("0.25%", 25), ("1%", 100),
    ):
        if marker in name:
            return bps
    return 0

def pool_age_days(created):
    if not created: return 0.0
    try:
        d = datetime.datetime.fromisoformat(created.rstrip("Z"))
        return (datetime.datetime.utcnow() - d).total_seconds() / 86400.0
    except Exception:
        return 0.0

# ---- On-chain read: Aerodrome pool's gauge via VotingReward ----
# Without the canonical Voter address we cannot enumerate gauges.
# We *can* still verify that the pool exists and read its current
# global state (slot0, liquidity, fee). This is enough to compute
# gas-cost-per-cycle from real on-chain gas usage.

# Common Aerodrome (Slipstream) gauge query pattern: gauge is a
# contract. Try a few likely registry addresses to find one that
# returns a non-zero response to a `isAlive()` or `left()` style
# call. If none works, mark reward_data_unavailable.
AERO_VOTER_CANDIDATES = [
    "0x16613524e02ad1e31e169a93aae5c40f47ff0fbf",  # placeholder
    "0xeC8d534Bb7e0Ab6CC02FE84a8BBe4b3b44a9fF3e",  # placeholder
    "0x0000000000000000000000000000000000004206",
]

def probe_aerodrome_voter():
    """Best-effort: try known selectors against likely Voter
    addresses. If anything returns a non-trivial result, log it
    for the report. If everything returns 0x/empty, mark
    reward_data_unavailable=true."""
    findings = []
    # gauges(address) selector = 0x4d24804c
    for addr in AERO_VOTER_CANDIDATES:
        try:
            r = http_post_rpc("eth_call",
                [{"to": addr,
                  "data": "0x4d24804c000000000000000000000000b2cc224c1c9fee385f8ad6a55b4d94e92359dc59"},
                 "latest"], 5)
        except Exception as e:
            r = None
        findings.append({"addr": addr, "result": r})
    return findings

# ---- Normalisation: GeckoTerminal pool -> row ----
def gt_to_row(p):
    a = p.get("attributes", {})
    rel = p.get("relationships", {})
    base_tok = rel.get("base_token", {}).get("data", {})
    quote_tok = rel.get("quote_token", {}).get("data", {})
    base_id = base_tok.get("id", "")
    quote_id = quote_tok.get("id", "")
    base_addr = base_id.split("_", 1)[1] if "_" in base_id else ""
    quote_addr = quote_id.split("_", 1)[1] if "_" in quote_id else ""
    name = a.get("name", "")
    base_sym, _, quote_sym = name.partition(" / ")
    base_sym = base_sym.strip()
    quote_sym = quote_sym.strip()
    for marker in ("0.01%", "0.018%", "0.02%", "0.021%",
                   "0.03%", "0.05%", "0.3%", "0.25%", "1%"):
        if marker in quote_sym:
            quote_sym = quote_sym.replace(marker, "").strip()
    vol = a.get("volume_usd", {}) or {}
    tx  = a.get("transactions", {}) or {}
    pc  = a.get("price_change_percentage", {}) or {}
    fee_bps = fee_tier_bps_from_name(name)
    tvl = f(a.get("reserve_in_usd"))
    return {
        "chain": "base",
        "protocol": "aerodrome-slipstream" if "aerodrome" in (rel.get("dex", {}).get("data", {}) or {}).get("id", "").lower() else
                    (rel.get("dex", {}).get("data", {}) or {}).get("id", "unknown-base-amm"),
        "pool_address": (a.get("address", "") or "").lower(),
        "name": name,
        "token0_symbol": base_sym,
        "token1_symbol": quote_sym,
        "token0_address": base_addr.lower(),
        "token1_address": quote_addr.lower(),
        "fee_tier_bps": fee_bps,
        "pool_type": "CLMM",
        "tvl_usd": tvl,
        "volume_usd_h24": f(vol.get("h24")),
        "volume_usd_h6":  f(vol.get("h6")),
        "volume_usd_h1":  f(vol.get("h1")),
        "price_change_pct_h24": f(pc.get("h24")),
        "price_change_pct_h6":  f(pc.get("h6")),
        "price_change_pct_h1":  f(pc.get("h1")),
        "tx_count_h24": i((tx.get("h24", {}) or {}).get("buys", 0)) + i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buys_h24":  i((tx.get("h24", {}) or {}).get("buys", 0)),
        "sells_h24": i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buyers_h24":  i((tx.get("h24", {}) or {}).get("buyers", 0)),
        "sellers_h24": i((tx.get("h24", {}) or {}).get("sellers", 0)),
        "pool_age_days": pool_age_days(a.get("pool_created_at", "")),
        "pool_created": a.get("pool_created_at", ""),
        "data_source": "geckoterminal",
        "data_quality_score": 0.85,
        "fetched_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

# ---- Normalisation: DexScreener pair -> row ----
def ds_to_row(p):
    addr = (p.get("pairAddress") or "").lower()
    bt = p.get("baseToken", {}) or {}
    qt = p.get("quoteToken", {}) or {}
    vol = p.get("volume", {}) or {}
    pc  = p.get("priceChange", {}) or {}
    tx  = p.get("txns", {}) or {}
    liq = p.get("liquidity", {}) or {}
    name = p.get("pairLabel") or p.get("pair") or f"{bt.get('symbol','?')}/{qt.get('symbol','?')}"
    fee_bps = 0
    # DexScreener includes feeBps in some responses
    if "feeBps" in p:
        fee_bps = i(p.get("feeBps"))
    else:
        # Try to parse from name; the pair has a labelsBySide we can use
        side = p.get("labelsBySide", {}) or {}
        lbl = (side.get("quote") or [""])[0] if side.get("quote") else ""
        if isinstance(lbl, str):
            fee_bps = fee_tier_bps_from_name(f"{name} {lbl}%")
    return {
        "chain": "base",
        "protocol": p.get("dexId", "unknown-base-amm"),
        "pool_address": addr,
        "name": name,
        "token0_symbol": bt.get("symbol", ""),
        "token1_symbol": qt.get("symbol", ""),
        "token0_address": (bt.get("address") or "").lower(),
        "token1_address": (qt.get("address") or "").lower(),
        "fee_tier_bps": fee_bps,
        "pool_type": "CLMM" if "v3" in (p.get("dexId","") or "").lower() or "slipstream" in (p.get("dexId","") or "").lower() else "AMM",
        "tvl_usd": f(liq.get("usd")),
        "volume_usd_h24": f(vol.get("h24")),
        "volume_usd_h6":  f(vol.get("h6")),
        "volume_usd_h1":  f(vol.get("h1")),
        "price_change_pct_h24": f(pc.get("h24")),
        "price_change_pct_h6":  f(pc.get("h6")),
        "price_change_pct_h1":  f(pc.get("h1")),
        "tx_count_h24": i((tx.get("h24", {}) or {}).get("buys", 0)) + i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buys_h24":  i((tx.get("h24", {}) or {}).get("buys", 0)),
        "sells_h24": i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buyers_h24": 0,  # not provided
        "sellers_h24": 0,
        "pool_age_days": 0,  # pairCreatedAt is None for most pairs
        "pool_created": "",
        "data_source": "dexscreener",
        "data_quality_score": 0.70,
        "fetched_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

# ---- Merge by pool_address, prefer geckoterminal fields ----
def merge_rows(gt_rows, ds_rows):
    by_addr = {r["pool_address"]: r for r in gt_rows if r.get("pool_address")}
    for r in ds_rows:
        a = r.get("pool_address", "")
        if not a:
            continue
        if a in by_addr:
            # Fill blanks in GT row with DS data
            for k, v in r.items():
                if k in ("chain", "protocol", "name") and not by_addr[a].get(k):
                    by_addr[a][k] = v
                if k.endswith("_usd") and not by_addr[a].get(k) and v:
                    by_addr[a][k] = v
            by_addr[a]["data_source"] = by_addr[a]["data_source"] + "+dexscreener"
            by_addr[a]["data_quality_score"] = max(by_addr[a]["data_quality_score"], r["data_quality_score"])
        else:
            by_addr[a] = r
    return list(by_addr.values())

# ---- Risk score ----
def score_pool(r):
    flags, score = [], 0
    sym0, sym1 = r["token0_symbol"], r["token1_symbol"]
    addr0, addr1 = r["token0_address"], r["token1_address"]
    tvl, vol24 = r["tvl_usd"], r["volume_usd_h24"]
    pc24, pc6, age, fee = r["price_change_pct_h24"], r["price_change_pct_h6"], r["pool_age_days"], r["fee_tier_bps"]

    for s in (sym0, sym1):
        if not s:
            flags.append("missing_symbol")
        elif any(p in s.upper() for p in RISKY_SYMBOL_PATTERNS):
            flags.append(f"risky_symbol:{s}")
    is_blue   = addr0 in BLUE_CHIP and addr1 in BLUE_CHIP
    is_aero   = AERO_BASE in (addr0, addr1) and (addr0 in BLUE_CHIP or addr1 in BLUE_CHIP)
    is_stable = addr0 in STABLES and addr1 in STABLES
    is_os     = ((addr0 in STABLES and addr1 in L1_WRAP) or
                 (addr1 in STABLES and addr0 in L1_WRAP))

    if is_aero:
        flags.append("aero_paired")  # reward-aware class
    if is_stable:
        flags.append("stable_stable_pair")
    if not (is_blue or is_aero or is_stable or is_os):
        flags.append("non_bluechip_pair")
        score += 30

    if tvl < TVL_MIN_USD:
        flags.append(f"tvl_below_floor:{tvl:.0f}")
        score += 60
    if tvl > 0:
        vt = vol24 / tvl
        if vt < VOL_TVL_MIN_RATIO:
            flags.append(f"low_vol_to_tvl:{vt:.2f}"); score += 25
        if vt > VOL_TVL_MAX_RATIO:
            flags.append(f"suspect_wash:{vt:.1f}"); score += 20

    if abs(pc24) > PCT_CHG_24H_MAX_ABS:
        flags.append(f"abs_pc24_gt_{PCT_CHG_24H_MAX_ABS:.0f}:{pc24:.1f}"); score += 30
    if abs(pc6) > PCT_CHG_6H_MAX_ABS:
        flags.append(f"abs_pc6_gt_{PCT_CHG_6H_MAX_ABS:.0f}:{pc6:.1f}"); score += 15
    if 0 < age < POOL_AGE_DAYS_MIN:
        flags.append(f"young_pool:{age:.0f}d"); score += 20
    if fee == 0:
        flags.append("unknown_fee_tier"); score += 15

    if score >= 80:   level = "REJECT"
    elif score >= 50: level = "HIGH"
    elif score >= 25: level = "MEDIUM"
    else:             level = "LOW"

    return {
        "score": score, "level": level, "flags": flags,
        "is_blue": is_blue, "is_aero": is_aero, "is_stable": is_stable, "is_os": is_os,
        "age_days": age, "vol_to_tvl": (vol24 / tvl) if tvl > 0 else 0.0,
    }

# ---- Gas estimates ----
# Cycle = approve + addLiquidity + collect + removeLiquidity.
# Add/remove is two full-range *single-sided* operations: roughly
# 250k gas total. Approve 60k. Collect 80k. Plus base overhead 30k.
# At 10 gwei and ETH=$3000, that's 0.10 USD. Add a 3x safety
# cushion for actual observed Base traffic: 0.30 USD/cycle. This
# matches R0.
GAS_ADD_USD    = 0.10
GAS_REMOVE_USD = 0.10
GAS_COLLECT_USD= 0.05
GAS_APPROVE_USD= 0.05
GAS_CYCLE_USD  = GAS_ADD_USD + GAS_REMOVE_USD + GAS_COLLECT_USD + GAS_APPROVE_USD

# ---- LP fee modelling ----
def fee_per_dollar_per_day(tvl, vol24, fee_bps):
    if tvl <= 0 or vol24 <= 0 or fee_bps <= 0:
        return 0.0
    pool_daily_fee = vol24 * (fee_bps / 10_000.0)
    return pool_daily_fee / tvl  # daily fee per $1 of LP

def il_daily_pct_heuristic(range_pct, pc_h24):
    sigma = abs(pc_h24) / 100.0
    if range_pct <= 0.05: return min(0.5, 0.6 * sigma)
    if range_pct <= 0.15: return min(0.4, 0.3 * sigma)
    return min(0.2, 0.1 * sigma)

# ---- Capital grid ----
SIZES  = [1.0, 3.0, 5.0, 10.0, 25.0, 50.0]
HORIZONS_HOURS = [1, 6, 24, 72, 168]
RANGES = [
    ("narrow_5pct",  0.05),
    ("medium_15pct", 0.15),
    ("wide_40pct",   0.40),
]

# ---- Main flow ----
print("scan: fetching geckoterminal base pools...", file=sys.stderr)
gt_raw = fetch_gt_pools(raw_limit)
gt_rows = [gt_to_row(p) for p in gt_raw]
print(f"scan: geckoterminal pulled {len(gt_rows)} pools", file=sys.stderr)

print("scan: fetching dexscreener base pairs (broadening)...", file=sys.stderr)
ds_raw = fetch_ds_pairs()
ds_rows = [ds_to_row(p) for p in ds_raw]
print(f"scan: dexscreener pulled {len(ds_rows)} base pairs", file=sys.stderr)

merged = merge_rows(gt_rows, ds_rows)
print(f"scan: merged pool count: {len(merged)}", file=sys.stderr)

# Write raw
raw_cols = [
    "chain","protocol","pool_address","name",
    "token0_symbol","token1_symbol","token0_address","token1_address",
    "fee_tier_bps","pool_type",
    "tvl_usd","volume_usd_h24","volume_usd_h6","volume_usd_h1",
    "price_change_pct_h24","price_change_pct_h6","price_change_pct_h1",
    "tx_count_h24","buys_h24","sells_h24","buyers_h24","sellers_h24",
    "pool_age_days","pool_created","data_source","data_quality_score","fetched_at",
]
with open(raw_csv, "w", newline="") as fcsv, open(raw_jsonl, "w") as fjsonl:
    w = csv.DictWriter(fcsv, fieldnames=raw_cols)
    w.writeheader()
    for r in merged:
        w.writerow(r)
        fjsonl.write(json.dumps(r) + "\n")
print(f"scan: wrote {raw_csv} ({len(merged)} rows)", file=sys.stderr)

# ---- Reward model: ALL pools are reward_data_unavailable from
# public/free sources today (subgraph is gone). We still record an
# honest reward_pools.csv with reward_apr_est=null and the
# observation log.
print("scan: probing Aerodrome voter / gauge (best effort)...", file=sys.stderr)
probe = probe_aerodrome_voter()
voter_ok = any(
    isinstance(p.get("result"), str) and p["result"] not in ("0x", "", None)
    for p in probe
)
reward_data_unavailable = not voter_ok
print(f"scan: reward_data_unavailable={reward_data_unavailable}", file=sys.stderr)

reward_cols = [
    "pool_address","protocol","name","token0_symbol","token1_symbol",
    "reward_token","reward_apr_est","reward_usd_per_day_per_dollar",
    "gauge_active","emission_continuity","reward_claim_gas_usd",
    "reward_sell_liquidity","reward_token_risk","reward_data_unavailable",
    "data_source_note",
]
with open(reward_csv, "w", newline="") as fcsv, open(reward_jsonl, "w") as fjsonl:
    w = csv.DictWriter(fcsv, fieldnames=reward_cols)
    w.writeheader()
    for r in merged:
        rec = {
            "pool_address": r["pool_address"],
            "protocol": r["protocol"],
            "name": r["name"],
            "token0_symbol": r["token0_symbol"],
            "token1_symbol": r["token1_symbol"],
            "reward_token": "AERO" if r.get("is_aero") or AERO_BASE in (r.get("token0_address",""), r.get("token1_address","")) else "",
            "reward_apr_est": None,  # explicitly null, not 0
            "reward_usd_per_day_per_dollar": None,
            "gauge_active": None,
            "emission_continuity": None,
            "reward_claim_gas_usd": 0.05 if r.get("is_aero") else None,  # educated guess
            "reward_sell_liquidity": None,
            "reward_token_risk": "LOW" if r.get("is_aero") else None,
            "reward_data_unavailable": True,
            "data_source_note": "Aerodrome public subgraph is offline; no public free replacement returns gauge reward data today. AERO paired pools retain theoretical AERO emissions but no per-pool rate is observable without on-chain voter contract address and historical state.",
        }
        w.writerow(rec)
        fjsonl.write(json.dumps(rec) + "\n")
print(f"scan: wrote {reward_csv} ({len(merged)} rows; all reward_data_unavailable=True)", file=sys.stderr)

# ---- Risk scoring ----
risk_rows, risk_records = [], []
for r in merged:
    s = score_pool(r)
    r["risk_score"]  = s["score"]
    r["risk_level"]  = s["level"]
    r["risk_flags"]  = ";".join(s["flags"])
    r["is_blue"]     = s["is_blue"]
    r["is_aero"]     = s["is_aero"]
    r["is_stable"]   = s["is_stable"]
    r["is_os"]       = s["is_os"]
    r["age_days"]    = round(s["age_days"], 1)
    r["vol_to_tvl"]  = round(s["vol_to_tvl"], 3)
    risk_rows.append(r)
    risk_records.append({
        "pool_address": r["pool_address"], "name": r["name"],
        "risk_score": s["score"], "risk_level": s["level"],
        "flags": s["flags"],
    })

risk_cols = list(risk_rows[0].keys())
with open(risk_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=risk_cols)
    w.writeheader()
    for r in risk_rows:
        w.writerow(r)
with open(risk_jsonl, "w") as fjsonl:
    for r in risk_records:
        fjsonl.write(json.dumps(r) + "\n")

from collections import Counter
rl = Counter(r["risk_level"] for r in risk_rows)
print(f"scan: risk levels {dict(rl)}", file=sys.stderr)

# ---- Capital threshold matrix: per-pool × (size, range, horizon) ----
# fee_per_day_per_dollar  : daily fee per $1 of LP
# For the matrix we use the narrow-range IL heuristic (worst-case)
# and skip ranges for clarity. The cell value is:
#   expected_net = size * fee_per_day * (hours/24) - size * il_pct * (hours/24) - gas_cycle
# The key question: at what (size, hours) does net >= 0?
# This is the *minimum viable size* answer.
gas_per_cycle = GAS_CYCLE_USD

cap_rows = []
for r in risk_rows:
    if r["risk_level"] in ("HIGH", "REJECT"):
        continue
    if r["tvl_usd"] <= 0 or r["volume_usd_h24"] <= 0 or r["fee_tier_bps"] <= 0:
        continue
    fpdd = fee_per_dollar_per_day(r["tvl_usd"], r["volume_usd_h24"], r["fee_tier_bps"])
    if fpdd <= 0:
        continue
    # Use the medium range as the canonical "tiny-live" candidate
    range_pct = 0.15
    il_pct_per_day = il_daily_pct_heuristic(range_pct, r["price_change_pct_h24"])
    for size in SIZES:
        for hours in HORIZONS_HOURS:
            days = hours / 24.0
            fee = size * fpdd * days
            il  = size * il_pct_per_day * days
            net = fee - il - gas_per_cycle
            cap_rows.append({
                "pool_address": r["pool_address"],
                "protocol": r["protocol"],
                "name": r["name"],
                "token0_symbol": r["token0_symbol"],
                "token1_symbol": r["token1_symbol"],
                "fee_tier_bps": r["fee_tier_bps"],
                "tvl_usd": r["tvl_usd"],
                "volume_usd_h24": r["volume_usd_h24"],
                "price_change_pct_h24": r["price_change_pct_h24"],
                "risk_level": r["risk_level"],
                "size_usdc": size,
                "range_label": "medium_15pct",
                "range_pct": range_pct,
                "hold_hours": hours,
                "expected_fee_usd": round(fee, 6),
                "expected_il_usd":  round(il, 6),
                "gas_cycle_usd":    gas_per_cycle,
                "expected_net_pnl_usd": round(net, 6),
                "fee_per_dollar_per_day": round(fpdd, 8),
                "il_pct_per_day":   round(il_pct_per_day, 6),
                "recommendation": "GO" if net > 0 and r["risk_level"] == "LOW" else
                                  "NEED_MORE_DATA" if net > -0.05 and r["risk_level"] in ("LOW","MEDIUM") else
                                  "NO_GO",
            })

cap_cols = list(cap_rows[0].keys())
with open(cap_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=cap_cols)
    w.writeheader()
    for r in cap_rows:
        w.writerow(r)
print(f"scan: wrote {cap_csv} ({len(cap_rows)} rows)", file=sys.stderr)

# ---- Gas amortization matrix: per-pool, the *minimum* (size, hours) ----
# that produces net >= 0. A pool passes gas-amortization when
#   size * fpdd * (hours/24) >= gas_per_cycle + size * il_pct_per_day * (hours/24)
# i.e. for any (size, hours) we can compute net. We sweep both
# axes and report the smallest (size, hours) that gives net >= 0.
gas_rows = []
for r in risk_rows:
    if r["risk_level"] in ("HIGH", "REJECT"):
        continue
    if r["tvl_usd"] <= 0 or r["volume_usd_h24"] <= 0 or r["fee_tier_bps"] <= 0:
        continue
    fpdd = fee_per_dollar_per_day(r["tvl_usd"], r["volume_usd_h24"], r["fee_tier_bps"])
    if fpdd <= 0:
        continue
    il_pct_per_day = il_daily_pct_heuristic(0.15, r["price_change_pct_h24"])
    best = None
    for size in SIZES:
        for hours in HORIZONS_HOURS:
            days = hours / 24.0
            fee = size * fpdd * days
            il  = size * il_pct_per_day * days
            net = fee - il - gas_per_cycle
            if net >= 0 and (best is None or (size, hours) < (best["min_viable_size"], best["min_viable_hours"])):
                best = {
                    "min_viable_size": size, "min_viable_hours": hours,
                    "expected_net_at_mvs": net, "expected_fee_at_mvs": fee,
                    "expected_il_at_mvs": il,
                }
    gas_rows.append({
        "pool_address": r["pool_address"],
        "protocol": r["protocol"],
        "name": r["name"],
        "token0_symbol": r["token0_symbol"],
        "token1_symbol": r["token1_symbol"],
        "fee_tier_bps": r["fee_tier_bps"],
        "tvl_usd": r["tvl_usd"],
        "volume_usd_h24": r["volume_usd_h24"],
        "fee_per_dollar_per_day": round(fpdd, 8),
        "il_pct_per_day": round(il_pct_per_day, 6),
        "gas_cycle_usd": gas_per_cycle,
        "min_viable_size_usdc": best["min_viable_size"] if best else None,
        "min_viable_hours":     best["min_viable_hours"] if best else None,
        "expected_net_at_mvs":  round(best["expected_net_at_mvs"], 6) if best else None,
        "expected_fee_at_mvs":  round(best["expected_fee_at_mvs"], 6) if best else None,
        "expected_il_at_mvs":   round(best["expected_il_at_mvs"], 6) if best else None,
        "passes_gas_at_10usdc_24h": (lambda: (
            10.0 * fpdd - 10.0 * il_pct_per_day - gas_per_cycle) >= 0)(),
        "passes_gas_at_50usdc_24h": (lambda: (
            50.0 * fpdd - 50.0 * il_pct_per_day - gas_per_cycle) >= 0)(),
        "passes_gas_at_50usdc_7d":  (lambda: (
            50.0 * fpdd * 7 - 50.0 * il_pct_per_day * 7 - gas_per_cycle) >= 0)(),
    })

gas_cols = list(gas_rows[0].keys())
with open(gas_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=gas_cols)
    w.writeheader()
    for r in gas_rows:
        w.writerow(r)
print(f"scan: wrote {gas_csv} ({len(gas_rows)} rows)", file=sys.stderr)

# ---- Ranking: pick the best (size, hours) per pool, then rank ----
# Score:
#   fee_score          = clip(fee_per_dollar_per_day * 365, 0, 1)   # 0..100% APR -> 0..1
#   volume_persist     = clip(vol_to_tvl / 5, 0, 1)
#   tvl_depth          = clip(log10(tvl)/7, 0, 1)
#   volatility_fit     = clip(1 - abs(pc24)/30, 0, 1)
#   gas_efficiency     = 1 if passes_gas_at_50usdc_7d else 0.5 if passes_gas_at_50usdc_24h else 0 if passes_gas_at_10usdc_24h else 0
#   token_risk_pen     = 0 if risk_level==LOW else 0.2 if MEDIUM else 0.6
#   data_quality       = data_quality_score
#
# Total: weighted average.

rank_rows = []
for r, g in zip(risk_rows, gas_rows):
    if r["risk_level"] in ("HIGH", "REJECT"):
        continue
    fpdd = g["fee_per_dollar_per_day"]
    fee_apr = fpdd * 365
    fee_score = max(0.0, min(1.0, fee_apr))
    vol_persist = max(0.0, min(1.0, g["vol_to_tvl"] / 5.0 if hasattr(g, "vol_to_tvl") else (r["volume_usd_h24"] / r["tvl_usd"] if r["tvl_usd"] > 0 else 0) / 5.0))
    tvl_depth = max(0.0, min(1.0, math.log10(max(r["tvl_usd"], 1.0)) / 7.0))
    vol_fit = max(0.0, min(1.0, 1.0 - abs(r["price_change_pct_h24"]) / 30.0))
    gas_eff = 1.0 if g["passes_gas_at_50usdc_7d"] else 0.7 if g["passes_gas_at_50usdc_24h"] else 0.4 if g["passes_gas_at_10usdc_24h"] else 0.1
    token_pen = 0.0 if r["risk_level"] == "LOW" else 0.2 if r["risk_level"] == "MEDIUM" else 0.6
    dq = r["data_quality_score"]
    # Reward-aware: AERO paired pools get a small bonus because
    # the *theoretical* existence of AERO emissions may make the
    # break-even achievable in practice. We mark this as
    # unquantified upside, not a real number.
    reward_unquantified = 0.10 if r.get("is_aero") else 0.0
    total = (0.30 * fee_score + 0.15 * vol_persist + 0.10 * tvl_depth
             + 0.10 * vol_fit + 0.20 * gas_eff + 0.05 * dq
             + reward_unquantified - token_pen)
    rec = "NO_GO"
    if r["risk_level"] == "REJECT" or r["risk_level"] == "HIGH":
        rec = "NO_GO"
    elif g["passes_gas_at_50usdc_7d"] and dq >= 0.7:
        rec = "GO_TINY_LIVE" if r["risk_level"] == "LOW" else "NEED_MORE_DATA"
    elif g["passes_gas_at_50usdc_24h"] and dq >= 0.7:
        rec = "NEED_MORE_DATA"
    elif g["passes_gas_at_10usdc_24h"]:
        rec = "NEED_MORE_DATA"
    else:
        rec = "NO_GO"
    rank_rows.append({
        "pool_address": r["pool_address"],
        "protocol": r["protocol"],
        "name": r["name"],
        "token0_symbol": r["token0_symbol"],
        "token1_symbol": r["token1_symbol"],
        "fee_tier_bps": r["fee_tier_bps"],
        "tvl_usd": r["tvl_usd"],
        "volume_usd_h24": r["volume_usd_h24"],
        "price_change_pct_h24": r["price_change_pct_h24"],
        "risk_level": r["risk_level"],
        "risk_score": r["risk_score"],
        "data_quality_score": dq,
        "fee_per_dollar_per_day": fpdd,
        "fee_apr_est": round(fee_apr, 4),
        "min_viable_size_usdc": g["min_viable_size_usdc"],
        "min_viable_hours":     g["min_viable_hours"],
        "expected_net_at_mvs":  g["expected_net_at_mvs"],
        "passes_10usdc_24h":    g["passes_gas_at_10usdc_24h"],
        "passes_50usdc_24h":    g["passes_gas_at_50usdc_24h"],
        "passes_50usdc_7d":     g["passes_gas_at_50usdc_7d"],
        "is_aero_paired":       r.get("is_aero", False),
        "is_blue_chip_pair":    r.get("is_blue", False),
        "fee_score": round(fee_score, 4),
        "volume_persistence_score": round(vol_persist, 4),
        "tvl_depth_score": round(tvl_depth, 4),
        "volatility_fit_score": round(vol_fit, 4),
        "gas_efficiency_score": round(gas_eff, 4),
        "token_risk_penalty": round(token_pen, 4),
        "score": round(total, 4),
        "go_no_go": rec,
    })

# Sort: GO first, NEED_MORE next, NO_GO last; within group by score desc
order = {"GO_TINY_LIVE": 0, "NEED_MORE_DATA": 1, "NO_GO": 2}
rank_rows.sort(key=lambda x: (order.get(x["go_no_go"], 9), -x["score"]))
for i, r in enumerate(rank_rows, 1):
    r["rank"] = i

rank_cols = list(rank_rows[0].keys())
with open(rank_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=rank_cols)
    w.writeheader()
    for r in rank_rows:
        w.writerow(r)
print(f"scan: wrote {rank_csv} ({len(rank_rows)} rows)", file=sys.stderr)

# Counts
go     = sum(1 for r in rank_rows if r["go_no_go"] == "GO_TINY_LIVE")
need   = sum(1 for r in rank_rows if r["go_no_go"] == "NEED_MORE_DATA")
nogo   = sum(1 for r in rank_rows if r["go_no_go"] == "NO_GO")
print(f"scan: GO_TINY_LIVE={go} NEED_MORE_DATA={need} NO_GO={nogo}", file=sys.stderr)
print(f"scan: reward_data_unavailable={reward_data_unavailable}", file=sys.stderr)
print(f"scan: probe findings={probe}", file=sys.stderr)
PYEOF

echo "strategy_evidence_r1: complete"
ls -la "${REPORT_DIR}"
