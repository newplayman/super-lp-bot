# Meteora Fee Capture Proxy — Stage E

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- scope: **partial_pool2_only (X/USDC)**

## 0. 关键说明

```text
rows                = 126 (6 notionals × 7 hold_windows × 3 fee_scenarios)
heuristic_marked    = true (no actual on-chain volume; scenario-based proxy)
real_fee_capture    = missing (not measured; mark 'heuristic')
proxy_methodology   = assumed_volume_pct × notional × base_fee_bps
```

## 1. Methodology (heuristic)

We do **NOT** have actual on-chain volume for X/USDC pool. Per spec, we use scenario-based proxies:

| scenario | assumed_volume_pct (per hold window) | rationale |
|---|---|---|
| low | 0.001 (0.1%) | conservative; minimal LP activity |
| medium | 0.005 (0.5%) | typical for active AMM pool with retail flow |
| high | 0.020 (2.0%) | aggressive; high-volume pool or 1-turnover-per-hold-window |

Formula per cell:
```
estimated_fee_capture_usd = notional × assumed_volume_pct × (base_fee_bps / 10000)
```

For X/USDC: base_fee_bps = 1.5 (V4 fee_snapshot); max_fee_bps = 10.

## 2. 示例 results (sample)

| notional | hold | scenario | assumed_volume | estimated_fee_usd |
|---|---|---|---|---|
| 10 | 1h | medium | 0.05 | 0.0000075 |
| 100 | 1h | medium | 0.5 | 0.000075 |
| 100 | 1h | high | 2.0 | 0.0003 |
| 1000 | 24h | high | 20.0 | 0.003 |
| 2000 | 24h | high | 40.0 | 0.006 |
| 2000 | 7d | high | 280.0 | 0.042 |

→ **Fee capture is TINY at all notionals** for X/USDC (because base_fee_bps=1.5 is low and assumed_volume is low for a single 1-pool feed).

## 3. Confidence

- confidence = 0.3 per row (heuristic-based)
- **NOT** real on-chain fee capture
- marker: `heuristic: true`, `invalid_reason: "no actual on-chain volume; scenario-based proxy; mark heuristic"`

## 4. 不在本阶段做

- ❌ 不测 actual on-chain volume
- ❌ 不 fake data
- ❌ 不 claim real fee capture

## 5. 安全断言

```text
this_stage_only_heuristic_proxy = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 6. 下一阶段

进入 Stage F — cost model (Solana tx fee + rent + position cost; 3 scenarios).
