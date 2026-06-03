# Solana Survival EV Model Adaptation — Stage I

- stage: `LP_SOLANA_LP_CONNECTOR_DESIGN_V1`
- run_id: `20260603_080347`

## 1. 哪些能复用 EVM V3 model

| EVM V3 组件 | 复用? | 说明 |
|---|---|---|
| **notional grid 10/20/100/500/1000/2000** | ✅ 完整复用 | USD amount；Solana 上 token decimal 可能不同 (USDC=6, SOL=9) 但 notional USD 不变 |
| **hold windows 15m/30m/1h/2h/6h/24h/7d** | ✅ 完整复用 | 时间维度不变 |
| **fee velocity** (proxy APR × volume) | ✅ 复用 framework | APR 数值不同；Solana DLMM typical 30-100% APR vs V3 20% APR (Base) |
| **cost model** (round trip cost) | ⚠️ 部分复用 | 复用 "cost" 字段语义；但 EVM gas 替换为 Solana rent + tx + priority fee |
| **near break-even** (within ±$0.01) | ✅ 完整复用 | threshold 不变 |
| **risk scoring** (0-1 with multiple components) | ✅ 复用 framework | 各 component 数值需重新 calibration |
| **5 scenarios** (zero_il_lvr, optimistic, realistic, conservative, stress) | ✅ 完整复用 | IL/LVR ratio 不变 (Meteora DLMM 在 stress 场景可能更低 due to binary IL) |
| **survival probability** (heuristic Gaussian half-normal) | ⚠️ 部分复用 | Meteora DLMM "0 IL until exit" → survival = 1 inside chosen bin range; 不需要 Gaussian |

## 2. 哪些不能复用 EVM V3

| EVM V3 组件 | 不能复用原因 | Solana 替代 |
|---|---|---|
| V3 tick math (sqrtPriceX96 / tick spacing / liquidity Q64.64) | Solana CLMM 字段相同但 layout 不同 | 重新实现 per protocol |
| EVM gas model (gas × gas_price) | Solana 用 rent + tx fee + priority fee | 见 3.1-3.6 |
| NFT position model (ERC721 token id) | Solana 多种 model (PDA / NFT mint / LP token) | 见 3.7 |
| feeGrowthInside model | Solana DLMM 用 dynamic_fee per bin; Orca 用 fee_growth_global_x64 | 重新实现 |
| QuoterV2 (Uniswap V3) | Solana 用 simulateTransaction / SDK quote | 用 `simulateTransaction(base64_swap_tx)` |
| ERC20 balanceOf / allowance | Solana 用 SPL token account + getTokenAccountBalance | 重新实现 |

## 3. Solana-specific 设计

### 3.1 rent / account costs

```python
def rent_required_sol(n_accounts_new: int) -> float:
    # rent_exemption_lamports = 890880 (typical account)
    # 1 SOL = 1e9 lamports
    return 890880 * n_accounts_new / 1e9
```

LP open 通常需要新建：
- 2 ATA (token A + token B) ≈ 2 * 890880 lamports = 0.0018 SOL
- 1 position account (Meteora DLMM) ≈ 890880 lamports = 0.00089 SOL
- 1 NFT mint (Orca / Raydium CLMM) ≈ 0.00144 SOL (NFT mint cost)
- → 0.0018-0.0032 SOL total rent on open

### 3.2 tx fee

```python
def base_tx_fee_sol(n_signatures: int) -> float:
    # 5000 lamports per signature
    return 5000 * n_signatures / 1e9
```

LP open tx 通常 1 signature; close = 1 signature.
→ 5000 lamports = 0.000005 SOL per tx = $0.00075 @ $150 SOL

### 3.3 priority fee

```python
def priority_fee_sol(n_cu: int, micro_lamports_per_cu: int) -> float:
    # Solana priority fee = cu_price * cu_limit
    return n_cu * micro_lamports_per_cu / 1e6 / 1e9
```

LP open tx ~ 200k-500k CU; priority ~ 1000-100000 micro-lamports/CU.
→ 200000 * 5000 / 1e6 / 1e9 = 0.001 SOL = $0.15 @ $150 SOL (实际多数 public RPC 默认 0)

### 3.4 token account creation cost

ATA 创建 = 0.00203928 SOL (rent-exempt minimum, slightly higher than typical)
→ 已含在 3.1 rent_required

### 3.5 account close recovery

```python
def rent_recovery_sol(n_accounts_closed: int) -> float:
    # 0.00089 SOL per closed account (return to wallet)
    return 890880 * n_accounts_closed / 1e9
```

LP close 时可关闭 position account + 2 ATA → 回收 0.0027 SOL
但 NFT mint 不能 close → NFT 路径 0 回收

### 3.6 position account / NFT cost

| 协议 | position 类型 | 不可回收 rent |
|---|---|---|
| Meteora DLMM | PDA account | 0 (PDA closeable) |
| Meteora DAMM v2 | PDA account | 0 |
| Orca Whirlpools | NFT mint | ~0.0014 SOL (NFT mint 不可 close) |
| Raydium CLMM | NFT mint | ~0.0014 SOL |
| Raydium CPMM | LP token | 0 (LP token burn = 关闭) |

### 3.7 liquidity range / bin model

| 协议 | range model |
|---|---|
| Meteora DLMM | bin range [lower_bin, upper_bin] |
| Meteora DAMM v2 | full range (constant product) |
| Orca Whirlpools | tick range [lower_tick, upper_tick] |
| Raydium CLMM | tick range [lower_tick, upper_tick] |
| Raydium CPMM | n/a (full range) |

### 3.8 exit cost

```python
def solana_lp_exit_cost_usd(notional_usd: float, protocol: str) -> float:
    # tx fee + priority fee + rent recovery (negative)
    base_tx = 0.000005 * 2  # 2 sigs
    priority = 0.0001       # nominal; actual 0-0.0001
    rent_recov = 0.0007 if protocol != "Orca Whirlpools" and protocol != "Raydium CLMM" else 0.0
    return (base_tx + priority - rent_recov) * 150  # convert to USD
```

### 3.9 slippage / route quote

- Solana quote via Jupiter Quote API or simulateTransaction
- Jupiter: 公开 REST; rate limit ~10 req/s; 适合 cache
- simulateTransaction: 不签名, 模拟 swap 输出

## 4. 复用 EVM V3 survival EV formula 框架

```python
def solana_survival_ev(
    notional_usd: float,
    hold_hours: float,
    fee_apr_proxy: float,
    il_lvr_ratio: float,           # 5 scenarios
    cost_round_trip_usd: float,    # Solana-specific
    slippage_bps: int,
    survival_probability: float,  # Solana-specific (DLMM: 1 if in bin; CLMM: Gaussian)
) -> dict:
    fee = notional_usd * fee_apr_proxy * (hold_hours / (365.0 * 24.0))
    il = fee * il_lvr_ratio
    slip = notional_usd * slippage_bps / 10000.0
    cost = cost_round_trip_usd
    expected = fee * survival_probability  # Solana-specific: DLMM = 0 fee if out of bin
    net = expected - il - cost - slip
    return {
        "expected_fee_usd": fee,
        "il_lvr_proxy_usd": il,
        "cost_proxy_usd": cost,
        "slippage_cost_usd": slip,
        "net_ev_proxy_usd": net,
        "net_ev_proxy_pct": (net / notional_usd) * 100.0 if notional_usd else 0.0,
        "survival_probability": survival_probability,
    }
```

## 5. 关键差异（Solana vs EVM V3 在 cost model 上）

| cost 维度 | EVM Base V3 | Solana Meteora DLMM | Solana Orca Whirlpools |
|---|---|---|---|
| tx fee | 0.0001-0.0005 | 0.00001 | 0.00001 |
| priority fee | n/a | 0-0.0001 (optional) | 0-0.0001 |
| rent (open) | 0 (no rent) | 0.0007-0.001 | 0.0007 + NFT 0.0014 |
| rent recovery (close) | 0 | -0.0007 | 0 (NFT not recoverable) |
| **round trip cost** | **0.012** | **0.0031** | **0.0048** |
| IL control | gradual | binary | gradual |
| expected fee APR proxy | 5-25% | 30-100% | 25-60% |
| **expected net EV at $10/7d** | **-0.046** (V3 Base) | **+0.01-0.05** (DLMM optimistic) | **+0.005-0.02** (Whirlpools optimistic) |

> 注：以上 EV 是 heuristic; 实际取决于 fee velocity 数据 + IL binary 假设是否成立；下一阶段 (read-only connector) 才能实证。

## 6. 不在本阶段做

- ❌ 实际跑 EV model on Solana data
- ❌ 写 Solana-specific formula 代码
- ❌ 跑 RPC
- ❌ 接 wallet

## 7. 安全断言

```text
this_stage_only_design_formula      = true
this_stage_does_not_run_rpc         = true
solana_wallet_or_keypair_touched    = false
can_run_probe_now                  = false
```
