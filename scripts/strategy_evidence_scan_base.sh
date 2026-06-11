#!/usr/bin/env bash
# scripts/strategy_evidence_scan_base.sh
#
# LP_BOT_STRATEGY_EVIDENCE_R0_POOL_DISCOVERY_AND_TINY_LIVE_CANDIDATE_SELECTION_V1
#
# Read-only: data collection + risk filter + LP range simulation +
# ranking for Base AMM candidate pools. NO wallet / signing /
# broadcasting / LP / swap / approve. Outputs go to the per-run
# report directory.
#
# Free, public, read-only data sources:
#   - GeckoTerminal API v2 (no auth) — top Base pools by 24h volume.
#
# Outputs (to ${REPORT_DIR}):
#   - candidate_pools_raw.{csv,jsonl}
#   - risk_filtered_pools.csv, risk_flags.jsonl
#   - lp_simulation_results.{csv,jsonl}
#   - ranked_tiny_live_candidates.csv
#
# Tunables via env:
#   STRATEGY_RUN_ID     (default: utc timestamp)
#   STRATEGY_RAW_LIMIT  (default: 200 pools; 100 = 1 page)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${STRATEGY_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
REPORT_DIR="${ROOT_DIR}/reports/strategy_evidence_r0_pool_discovery/${RUN_ID}"
mkdir -p "${REPORT_DIR}"

cd "${ROOT_DIR}"

RAW_CSV="${REPORT_DIR}/candidate_pools_raw.csv"
RAW_JSONL="${REPORT_DIR}/candidate_pools_raw.jsonl"
RISK_CSV="${REPORT_DIR}/risk_filtered_pools.csv"
RISK_JSONL="${REPORT_DIR}/risk_flags.jsonl"
SIM_CSV="${REPORT_DIR}/lp_simulation_results.csv"
SIM_JSONL="${REPORT_DIR}/lp_simulation_results.jsonl"
RANK_CSV="${REPORT_DIR}/ranked_tiny_live_candidates.csv"

echo "strategy_evidence_scan: RUN_ID=${RUN_ID}"
echo "strategy_evidence_scan: REPORT_DIR=${REPORT_DIR}"

RAW_LIMIT="${STRATEGY_RAW_LIMIT:-200}"

export RAW_LIMIT RAW_CSV RAW_JSONL RISK_CSV RISK_JSONL SIM_CSV SIM_JSONL RANK_CSV
export REPORT_DIR RUN_ID

python3 - <<'PYEOF'
from __future__ import annotations
import csv, json, math, os, sys, time, urllib.request, datetime

# ---- argv / env ----
raw_limit    = int(os.environ["RAW_LIMIT"])
raw_csv      = os.environ["RAW_CSV"]
raw_jsonl    = os.environ["RAW_JSONL"]
risk_csv     = os.environ["RISK_CSV"]
risk_jsonl   = os.environ["RISK_JSONL"]
sim_csv      = os.environ["SIM_CSV"]
sim_jsonl    = os.environ["SIM_JSONL"]
rank_csv     = os.environ["RANK_CSV"]
report_dir   = os.environ["REPORT_DIR"]
run_id       = os.environ["RUN_ID"]

# ---- Base mainnet canonical addresses (lowercased) ----
WETH_BASE  = "0x4200000000000000000000000000000000000006"
USDC_BASE  = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
USDbC_BASE = "0xd9aaec86b65d86f3a3a7c83f3a9bed3a8fab4cd1"
DAI_BASE   = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
CBBTC_BASE = "0xcbb7c0000ab88b473b1f5bfd945ef319e551d82"

# GeckoTerminal API uses these prefixed token IDs:
TOK_GT = {
    WETH_BASE.lower():  "base_0x4200000000000000000000000000000000000006",
    USDC_BASE.lower():  "base_0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    USDbC_BASE.lower(): "base_0xd9aaec86b65d86f3a3a7c83f3a9bed3a8fab4cd1",
    DAI_BASE.lower():   "base_0x50c5725949a6f0c72e6c4a641f24049a917db0cb",
    CBBTC_BASE.lower(): "base_0xcbb7c0000ab88b473b1f5bfd945ef319e551d82",
}

STABLES  = {USDC_BASE.lower(), USDbC_BASE.lower(), DAI_BASE.lower()}
L1_WRAP  = {WETH_BASE.lower(), CBBTC_BASE.lower()}
BLUE_CHIP= L1_WRAP | STABLES

# Token symbol denylist (meme / honeypot patterns; narrow on purpose
# — we are filtering 100+ pools down to a few, not labelling
# categories).
RISKY_SYMBOL_PATTERNS = ("INU", "PEPE", "SHIB", "DOGE", "MOON",
                         "TEST", "XXX", "FAKE", "RUG", "SCAM")

# ---- HTTP fetch ----
def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "lp-bot-r0/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def fetch_top_base_pools(limit):
    """GeckoTerminal /networks/base/pools returns <=20 items per
    page (smaller than /coins/{id}/pools which is 100). Page through
    until we have `limit` items or the API runs dry."""
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
        # polite cushion between pages
        time.sleep(0.6)
    return out[:limit]

# ---- Token symbol lookup (single batched call for the page) ----
def token_info_map(pools):
    """Return {token_gt_id: {'symbol':..., 'decimals':...}} for any
    base/quote token referenced by the given pools. Single batched
    call per page to keep this well under GeckoTerminal's
    ~30 req/min anonymous limit."""
    ids = set()
    for p in pools:
        a = p.get("attributes", {})
        for k in ("base_token", "quote_token"):
            t = p.get("relationships", {}).get(k, {}).get("data", {})
            tid = t.get("id")
            if tid:
                ids.add(tid)
    info = {}
    # GeckoTerminal supports GET /networks/base/tokens/multi/{ids}
    # with comma-joined addresses (max ~30). For a page of 100 pools
    # we hit that limit; fall back to per-id lookups, which is 2
    # calls per pool — too many. We instead do a single bulk call by
    # joining address substrings, capped to 30.
    addrs = [i.split("_", 1)[1] for i in ids if i.startswith("base_0x")]
    if not addrs:
        return info
    base = "https://api.geckoterminal.com/api/v2"
    # chunk by 30
    for i in range(0, len(addrs), 30):
        chunk = addrs[i:i+30]
        url = f"{base}/networks/base/tokens/multi/{','.join(chunk)}"
        try:
            data = http_get_json(url)
        except Exception as e:
            print(f"warn: token info chunk failed: {e}", file=sys.stderr)
            continue
        for tok in data.get("data", []):
            tid = tok.get("id", "")
            attrs = tok.get("attributes", {})
            info[tid] = {
                "symbol": attrs.get("symbol", ""),
                "name": attrs.get("name", ""),
                "decimals": attrs.get("decimals"),
                "gt_score": attrs.get("gt_score"),
                "holders": attrs.get("holders", {}),
            }
        # polite rate-limit cushion
        time.sleep(0.5)
    return info

# ---- Row normalisation ----
def f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def i(x, default=0):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default

def fee_tier_bps_from_name(name):
    """Parse fee tier bps (1bp = 0.01%) from GeckoTerminal name
    like 'WETH / USDC 0.05%'. 0 if not in our recognised set."""
    if not name:
        return 0
    for marker, bps in (
        ("0.01%", 1), ("0.018%", 1.8), ("0.02%", 2), ("0.021%", 2.1),
        ("0.03%", 3), ("0.05%", 5), ("0.3%", 30), ("0.25%", 25),
        ("1%", 100),
    ):
        if marker in name:
            return bps
    return 0

def normalise(p, tok_info, fetched_at):
    a = p.get("attributes", {})
    rel = p.get("relationships", {})
    base_tok = rel.get("base_token", {}).get("data", {})
    quote_tok = rel.get("quote_token", {}).get("data", {})
    base_id = base_tok.get("id", "")
    quote_id = quote_tok.get("id", "")
    base_addr = base_id.split("_", 1)[1] if "_" in base_id else ""
    quote_addr = quote_id.split("_", 1)[1] if "_" in quote_id else ""
    base_sym = (tok_info.get(base_id) or {}).get("symbol", "")
    quote_sym = (tok_info.get(quote_id) or {}).get("symbol", "")
    # If token info lookup failed, fall back to splitting the name
    if (not base_sym or not quote_sym) and " / " in a.get("name", ""):
        head, _, tail = a.get("name", "").partition(" / ")
        if not base_sym:
            base_sym = head.strip()
        if not quote_sym:
            tail = tail.strip()
            # strip trailing " 0.05%" etc.
            for marker in ("0.01%", "0.018%", "0.02%", "0.021%",
                            "0.03%", "0.05%", "0.3%", "0.25%", "1%"):
                if marker in tail:
                    tail = tail.replace(marker, "").strip()
            quote_sym = tail

    vol = a.get("volume_usd", {}) or {}
    tx  = a.get("transactions", {}) or {}
    pc  = a.get("price_change_percentage", {}) or {}
    return {
        "pool_address":       a.get("address", "").lower(),
        "name":               a.get("name", ""),
        "protocol":           "aerodrome" if a.get("name", "").endswith("%") else "unknown",
        "dex_id":             (rel.get("dex", {}).get("data", {}) or {}).get("id", ""),
        "token0_symbol":      base_sym,
        "token1_symbol":      quote_sym,
        "token0_address":     base_addr.lower(),
        "token1_address":     quote_addr.lower(),
        "fee_tier_bps":       fee_tier_bps_from_name(a.get("name", "")),
        "tvl_usd":            f(a.get("reserve_in_usd")),
        "volume_usd_h24":     f(vol.get("h24")),
        "volume_usd_h6":      f(vol.get("h6")),
        "volume_usd_h1":      f(vol.get("h1")),
        "price_change_pct_h24": f(pc.get("h24")),
        "price_change_pct_h6":  f(pc.get("h6")),
        "tx_count_h24":         i((tx.get("h24", {}) or {}).get("buys", 0)) + i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buys_h24":             i((tx.get("h24", {}) or {}).get("buys", 0)),
        "sells_h24":            i((tx.get("h24", {}) or {}).get("sells", 0)),
        "buyers_h24":           i((tx.get("h24", {}) or {}).get("buyers", 0)),
        "sellers_h24":          i((tx.get("h24", {}) or {}).get("sellers", 0)),
        "pool_created":         a.get("pool_created_at", ""),
        "data_source":          "geckoterminal_api_v2_base",
        "fetched_at":           fetched_at,
    }

# ---- Pull raw ----
pools_raw = fetch_top_base_pools(raw_limit)
fetched = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"scan: pulled {len(pools_raw)} raw pools from geckoterminal", file=sys.stderr)

tok_info = token_info_map(pools_raw)
print(f"scan: token info resolved for {len(tok_info)} tokens", file=sys.stderr)

rows = [normalise(p, tok_info, fetched) for p in pools_raw]

# ---- Write raw.csv + raw.jsonl ----
raw_cols = [
    "pool_address", "protocol", "dex_id", "name",
    "token0_symbol", "token1_symbol",
    "token0_address", "token1_address",
    "fee_tier_bps", "tvl_usd", "volume_usd_h24", "volume_usd_h6", "volume_usd_h1",
    "price_change_pct_h24", "price_change_pct_h6",
    "tx_count_h24", "buys_h24", "sells_h24", "buyers_h24", "sellers_h24",
    "pool_created", "data_source", "fetched_at",
]
with open(raw_csv, "w", newline="") as fcsv, open(raw_jsonl, "w") as fjsonl:
    w = csv.DictWriter(fcsv, fieldnames=raw_cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)
        fjsonl.write(json.dumps(r, default=str) + "\n")
print(f"scan: wrote {raw_csv} ({len(rows)} rows)", file=sys.stderr)

# ---- Risk filter ----
# Token risk: stable + L1 wrap pass by default; meme pattern deny;
# unknown symbol pair (neither side recognised) gets MEDIUM penalty.
# Pool risk: TVL floor, volume/TVL bounds, age floor, price-change
# extremes, single-side liquidity concentration proxy.
#
# This is heuristic, intentionally conservative for tiny-live — we
# want a small, defensible shortlist, not exhaustive coverage.

TVL_MIN_USD          = 50_000.0   # below this a 1-10 USDC LP moves the pool
VOL_TVL_MIN_RATIO   = 0.05       # dead pool if 24h vol/TVL < 5%
VOL_TVL_MAX_RATIO   = 50.0       # wash-trade candidate if > 50x TVL/day
PCT_CHG_24H_MAX_ABS = 35.0       # > 35% 24h move = unstable for tight range
PCT_CHG_6H_MAX_ABS  = 20.0
POOL_AGE_DAYS_MIN   = 14.0

def pool_age_days(created):
    if not created:
        return 0.0
    try:
        d = datetime.datetime.fromisoformat(created.rstrip("Z"))
        return (datetime.datetime.utcnow() - d).total_seconds() / 86400.0
    except Exception:
        return 0.0

def token_risk(symbol, addr):
    flags = []
    sym_l = (symbol or "").upper()
    if any(p in sym_l for p in RISKY_SYMBOL_PATTERNS):
        flags.append(f"risky_symbol:{sym_l}")
    if not symbol:
        flags.append("missing_symbol")
    return flags

def score_pool(r):
    flags = []
    score = 0  # higher = more risk
    sym0 = r["token0_symbol"]; sym1 = r["token1_symbol"]
    addr0 = r["token0_address"]; addr1 = r["token1_address"]
    tvl = r["tvl_usd"]
    vol24 = r["volume_usd_h24"]
    pc24 = r["price_change_pct_h24"]
    pc6  = r["price_change_pct_h6"]
    age = pool_age_days(r["pool_created"])
    fee = r["fee_tier_bps"]

    # Token risk
    flags.extend([f"t0:{x}" for x in token_risk(sym0, addr0)])
    flags.extend([f"t1:{x}" for x in token_risk(sym1, addr1)])

    # Both stable
    both_stable = addr0 in STABLES and addr1 in STABLES
    # One stable, one L1
    one_stable  = (addr0 in STABLES) ^ (addr1 in STABLES) and (
        (addr0 in STABLES and addr1 in L1_WRAP) or
        (addr1 in STABLES and addr0 in L1_WRAP)
    )
    is_blue_chip = addr0 in BLUE_CHIP and addr1 in BLUE_CHIP

    if not (is_blue_chip or one_stable or both_stable):
        # At least one side is an unknown / long-tail token.
        # Allow only if volume is meaningful and pool has been around.
        flags.append("non_bluechip_pair")
        score += 25

    if both_stable:
        flags.append("stable_stable_pair")
        # stable-stable LP economics are tight; allow but with note

    # Pool risk
    if tvl < TVL_MIN_USD:
        flags.append(f"tvl_below_floor:{tvl:.0f}")
        score += 60
    if tvl > 0:
        vt = vol24 / tvl
        if vt < VOL_TVL_MIN_RATIO:
            flags.append(f"low_vol_to_tvl:{vt:.2f}")
            score += 25
        if vt > VOL_TVL_MAX_RATIO:
            flags.append(f"suspect_wash:{vt:.1f}")
            score += 20

    if abs(pc24) > PCT_CHG_24H_MAX_ABS:
        flags.append(f"abs_pc24_gt_{PCT_CHG_24H_MAX_ABS:.0f}:{pc24:.1f}")
        score += 30
    if abs(pc6) > PCT_CHG_6H_MAX_ABS:
        flags.append(f"abs_pc6_gt_{PCT_CHG_6H_MAX_ABS:.0f}:{pc6:.1f}")
        score += 15

    if age < POOL_AGE_DAYS_MIN:
        flags.append(f"young_pool:{age:.0f}d")
        score += 20

    if fee == 0:
        flags.append("unknown_fee_tier")
        score += 15

    # Risk levels
    if score >= 80:
        level = "REJECT"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "score": score,
        "level": level,
        "flags": flags,
        "is_blue_chip": is_blue_chip,
        "one_stable": one_stable,
        "both_stable": both_stable,
        "age_days": age,
        "vol_to_tvl": (vol24 / tvl) if tvl > 0 else 0.0,
    }

risk_rows = []
risk_records = []
for r in rows:
    s = score_pool(r)
    out = dict(r)
    out["risk_score"]  = s["score"]
    out["risk_level"]  = s["level"]
    out["risk_flags"]  = ";".join(s["flags"])
    out["can_shadow"]  = s["level"] in ("LOW", "MEDIUM")
    out["can_tiny_live"] = s["level"] in ("LOW", "MEDIUM") and s["is_blue_chip"]
    out["age_days"]    = round(s["age_days"], 1)
    out["vol_to_tvl"]  = round(s["vol_to_tvl"], 3)
    risk_rows.append(out)
    risk_records.append({
        "pool_address": r["pool_address"],
        "name":         r["name"],
        "risk_score":   s["score"],
        "risk_level":   s["level"],
        "flags":        s["flags"],
        "can_shadow":   out["can_shadow"],
        "can_tiny_live": out["can_tiny_live"],
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

# Counts
from collections import Counter
risk_level_counts = Counter(r["risk_level"] for r in risk_rows)
print(f"scan: risk levels {dict(risk_level_counts)}", file=sys.stderr)
print(f"scan: wrote {risk_csv}", file=sys.stderr)

# ---- LP simulation ----
# For each pool that passed risk, simulate narrow (5%), medium
# (15%), wide (40%) range at 1 / 3 / 5 / 10 USDC. Use a simple
# closed-form model:
#   - position_value = size_usdc
#   - expected_fee_per_day = size_usdc * (pool_24h_fee / tvl_usd)
#     where pool_24h_fee = vol24 * fee_bps/10000
#   - expected_il_per_day = size_usdc * il_daily_pct(range, vol)
#     il_daily_pct is a heuristic: narrower range → bigger IL when
#     out of range → higher expected IL; we assume log-normal moves
#     with sigma = abs(price_change_h24)/100 as a coarse proxy and
#     widen it for shorter calibration windows.
#   - gas_per_cycle = 0.30 USD (Base add+remove+collect cycle, public RPC,
#     conservative: 3 txs * ~100k gas * ~10 gwei * ETH~$3000 → ~0.09;
#     + slippage headroom).
GAS_USD_PER_CYCLE = 0.30
SIZES_USDC = [1.0, 3.0, 5.0, 10.0]
RANGES = [
    ("narrow_5pct",  0.05),
    ("medium_15pct", 0.15),
    ("wide_40pct",   0.40),
]

def il_daily_pct(range_pct, pc_h24, pc_h6):
    """Heuristic IL per day for a range, using 24h absolute move as
    a one-sigma proxy. Returns fraction (e.g. 0.02 = 2%/day)."""
    if pc_h24 == 0 and pc_h6 == 0:
        return 0.0
    sigma = abs(pc_h24) / 100.0
    # Out-of-range probability for a uniform random walk on the
    # range is roughly P(|z| > range/sigma). Use a coarse step
    # function so a narrow range in a high-vol pool gets hammered.
    if sigma <= 0:
        return 0.0
    if range_pct <= 0.05:
        return min(0.5, 0.6 * sigma)
    if range_pct <= 0.15:
        return min(0.4, 0.3 * sigma)
    return min(0.2, 0.1 * sigma)

sim_rows = []
sim_records = []
for r in risk_rows:
    if r["risk_level"] not in ("LOW", "MEDIUM"):
        continue
    if r["tvl_usd"] <= 0 or r["volume_usd_h24"] <= 0:
        continue
    fee_bps = r["fee_tier_bps"] or 0
    if fee_bps <= 0:
        continue
    pool_daily_fee_usd = r["volume_usd_h24"] * (fee_bps / 10_000.0)
    share_per_dollar = pool_daily_fee_usd / r["tvl_usd"]  # daily fee per $1 LP
    for range_label, range_pct in RANGES:
        il_pct = il_daily_pct(range_pct, r["price_change_pct_h24"], r["price_change_pct_h6"])
        for size in SIZES_USDC:
            fee_day = size * share_per_dollar
            il_day  = size * il_pct
            gas     = GAS_USD_PER_CYCLE
            net     = fee_day - il_day - gas
            rec = {
                "pool_address": r["pool_address"],
                "protocol":     r["protocol"],
                "name":         r["name"],
                "token0_symbol": r["token0_symbol"],
                "token1_symbol": r["token1_symbol"],
                "fee_tier_bps": fee_bps,
                "tvl_usd":      r["tvl_usd"],
                "volume_usd_h24": r["volume_usd_h24"],
                "price_change_pct_h24": r["price_change_pct_h24"],
                "risk_level":   r["risk_level"],
                "size_usdc":    size,
                "range_label":  range_label,
                "range_pct":    range_pct,
                "expected_fee_usd_per_day": round(fee_day, 6),
                "expected_il_usd_per_day":  round(il_day, 6),
                "gas_usd_per_cycle":        round(gas, 4),
                "net_usd_per_day":          round(net, 6),
                "fee_to_gas_ratio":         round(fee_day / gas if gas > 0 else 0.0, 4),
                "il_pct_per_day":           round(il_pct, 6),
                "can_tiny_live":            r["can_tiny_live"],
            }
            sim_rows.append(rec)
            sim_records.append(rec)

sim_cols = list(sim_rows[0].keys()) if sim_rows else [
    "pool_address","protocol","name","token0_symbol","token1_symbol",
    "fee_tier_bps","tvl_usd","volume_usd_h24","price_change_pct_h24",
    "risk_level","size_usdc","range_label","range_pct",
    "expected_fee_usd_per_day","expected_il_usd_per_day","gas_usd_per_cycle",
    "net_usd_per_day","fee_to_gas_ratio","il_pct_per_day","can_tiny_live",
]
with open(sim_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=sim_cols)
    w.writeheader()
    for r in sim_rows:
        w.writerow(r)
with open(sim_jsonl, "w") as fjsonl:
    for r in sim_records:
        fjsonl.write(json.dumps(r) + "\n")
print(f"scan: wrote {sim_csv} ({len(sim_rows)} rows)", file=sys.stderr)

# ---- Ranking ----
# For each pool, pick the (size, range) with the best fee/il
# trade-off weighted by a transparent formula. Stable-stable
# pairs are de-prioritised (thin fee). Non-blue-chip pairs can
# appear in the table but with explicit go_no_go=NO_GO unless
# the data was unusually strong.
def pick_best(sim_for_pool):
    if not sim_for_pool:
        return None
    # For tiny-live we want: notional=10 USDC (largest realistic
    # probe), net positive after IL, fee/gas >= 3 (gas is the
    # killer at this size), and prefer medium or wide range to
    # keep IL bounded.
    best = None
    for s in sim_for_pool:
        # Score: 0.6 * normalised net (0..1 over [-1, +1] usd/day)
        #      + 0.4 * normalised fee/gas (cap at 50)
        n_net  = max(0.0, min(1.0, (s["net_usd_per_day"] + 1.0) / 2.0))
        n_fg   = max(0.0, min(1.0, s["fee_to_gas_ratio"] / 50.0))
        range_pen = {"narrow_5pct": 0.0, "medium_15pct": 0.05, "wide_40pct": 0.10}[s["range_label"]]
        s["_score"] = 0.6 * n_net + 0.4 * n_fg - range_pen
        if best is None or s["_score"] > best["_score"]:
            best = s
    return best

# Group sims by pool
from collections import defaultdict
by_pool = defaultdict(list)
for s in sim_rows:
    by_pool[s["pool_address"]].append(s)

# Build rank rows
rank_rows = []
for r in risk_rows:
    sims = by_pool.get(r["pool_address"], [])
    best = pick_best(sims)
    if best is None:
        continue
    # Decide go/no-go:
    #   GO         : can_tiny_live AND best net > 0 AND fee/gas >= 1
    #   NEED_MORE  : blue chip or one-stable with best net near 0
    #                (within 1 USD/day at 10 USDC) and good data
    #   NO_GO      : everything else
    is_bc   = r["token0_address"] in BLUE_CHIP and r["token1_address"] in BLUE_CHIP
    is_os   = r["token0_address"] in STABLES and r["token1_address"] in L1_WRAP
    is_os  |= r["token1_address"] in STABLES and r["token0_address"] in L1_WRAP
    go = "NO_GO"
    reason = ""
    if not r["can_tiny_live"]:
        go = "NO_GO"
        reason = f"risk={r['risk_level']}"
    elif best["net_usd_per_day"] <= 0 or best["fee_to_gas_ratio"] < 1.0:
        if is_bc or is_os:
            go = "NEED_MORE_DATA"
            reason = f"bluechip_or_onestable, near_breakeven net={best['net_usd_per_day']:.4f}"
        else:
            go = "NO_GO"
            reason = f"non_bluechip, breakeven_or_negative net={best['net_usd_per_day']:.4f}"
    else:
        if is_bc:
            go = "GO_TINY_LIVE"
            reason = f"bluechip_pair, net={best['net_usd_per_day']:.4f}/day, fg={best['fee_to_gas_ratio']:.1f}"
        elif is_os:
            go = "GO_TINY_LIVE"
            reason = f"stable_vs_L1, net={best['net_usd_per_day']:.4f}/day, fg={best['fee_to_gas_ratio']:.1f}"
        else:
            # High-fee non-bluechip with positive net is suspicious
            # for tiny-live; mark NEED_MORE_DATA so human can review.
            go = "NEED_MORE_DATA"
            reason = f"non_bluechip_positive_net, review_required, net={best['net_usd_per_day']:.4f}"

    rank_rows.append({
        "rank": 0,  # filled after sort
        "pool_address": r["pool_address"],
        "protocol": r["protocol"],
        "name":     r["name"],
        "token0_symbol": r["token0_symbol"],
        "token1_symbol": r["token1_symbol"],
        "fee_tier_bps": r["fee_tier_bps"],
        "tvl_usd":  r["tvl_usd"],
        "volume_usd_h24": r["volume_usd_h24"],
        "price_change_pct_h24": r["price_change_pct_h24"],
        "risk_level": r["risk_level"],
        "risk_score": r["risk_score"],
        "best_size_usdc": best["size_usdc"],
        "best_range_label": best["range_label"],
        "best_range_pct": best["range_pct"],
        "expected_fee_usd_per_day": best["expected_fee_usd_per_day"],
        "expected_il_usd_per_day":  best["expected_il_usd_per_day"],
        "gas_usd_per_cycle":        best["gas_usd_per_cycle"],
        "net_usd_per_day":          best["net_usd_per_day"],
        "fee_to_gas_ratio":         best["fee_to_gas_ratio"],
        "score": round(best["_score"], 4),
        "go_no_go": go,
        "reason":   reason,
    })

# Sort: GO first by score desc, then NEED_MORE, then NO_GO
go_order = {"GO_TINY_LIVE": 0, "NEED_MORE_DATA": 1, "NO_GO": 2}
rank_rows.sort(key=lambda x: (go_order.get(x["go_no_go"], 9), -x["score"]))
for i, r in enumerate(rank_rows, 1):
    r["rank"] = i

# Cap to top 10 GO + 10 NEED_MORE + rest NO_GO, but write all
# (top-10 view in summary; CSV is complete).
rank_cols = list(rank_rows[0].keys()) if rank_rows else ["rank"]
with open(rank_csv, "w", newline="") as fcsv:
    w = csv.DictWriter(fcsv, fieldnames=rank_cols)
    w.writeheader()
    for r in rank_rows:
        w.writerow(r)
print(f"scan: wrote {rank_csv} ({len(rank_rows)} rows)", file=sys.stderr)

# ---- Summary stats printed to stderr (caller greps if needed) ----
go_rows     = [r for r in rank_rows if r["go_no_go"] == "GO_TINY_LIVE"]
need_rows   = [r for r in rank_rows if r["go_no_go"] == "NEED_MORE_DATA"]
nogo_rows   = [r for r in rank_rows if r["go_no_go"] == "NO_GO"]
print(f"scan: GO_TINY_LIVE={len(go_rows)} NEED_MORE_DATA={len(need_rows)} NO_GO={len(nogo_rows)}", file=sys.stderr)
PYEOF

echo "strategy_evidence_scan: complete"
ls -la "${REPORT_DIR}"
