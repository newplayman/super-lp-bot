# Fee Estimation Basis (R0 proxy, no actual fee)

- node: 6h
- run_id: 20260605_043726
- actual_fee_data_available: **false**
- fee_proxy_used: **true**
- heuristic_used: **true**

R0 阶段所有 fee 数字 = proxy / heuristic, 不是 actual fee. 实际 fee 必须有 tokenId + feeGrowth snapshot + tokensOwed 实测.

## 公式

### V3 / CLMM

```
fee_proxy_<width> = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_<width>
```

### Meteora DLMM

```
fee_proxy_<coverage> = volume_window × fee_rate × user_bin_share_in_range_<coverage>
```

### CPMM

```
fee_proxy = volume_window × fee_rate × user_lp_share
user_lp_share = user_notional / pool_tvl
```

### Stable / LST-Stable

```
fee_proxy = volume_window × fee_rate × user_lp_share (assumes low IL)
adjusted_il = il_base × (1 + depeg_risk_score × 2)
```

## R0 限制

- ❌ 无 tokenId / positionId
- ❌ 无 feeGrowth snapshot
- ❌ 无 tokensOwed
- ❌ 无实际 add/remove 成本
- ❌ 无 realized PnL
