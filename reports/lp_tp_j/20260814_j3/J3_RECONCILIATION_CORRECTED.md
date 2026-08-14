# TP-J FIX-J3 — 更正 CLMM 换腿成本后的逐项对账

本报告只读 paper runner 输出和已存 scanner SQLite 快照；不调用 RPC、不触碰 runner 或保护进程。
NetCover 收益/IL输入使用 runner 的真实累计观测；未被 runner 记账的成本明确标为 `UNMODELED`，绝不按 $0 处理。

## 6 仓总览

|池|资金|持有 h|paper 净 PnL|NetCover 收入|NetCover 风险|NetCover|≥1.0|快照来源|
|---|---:|---:|---:|---:|---:|---:|---|---|
|WETH-CBBTC (aerodrome-slipstream)|$3207.66|1220.40|$206.7600|$102.7969|$168.3441|0.610635|否|reports/lp_funnel_autopsy/20260810_043427/scanner.db @ 2026-08-10T04:34:39.491608+00:00|
|WETH-USDC (aerodrome-slipstream)|$2912.46|1220.40|$1216.7900|$982.5505|$119.1020|8.249658|是|reports/lp_tp_d/20260810_d4_top68_w10_normal/scanner.db @ 2026-08-10T13:24:29.678852+00:00|
|WETH-USDC (uniswap-v3)|$879.89|1220.40|$111.0200|$87.6535|$55.9057|1.567880|是|reports/lp_scanner/scanner.db @ 2026-08-13T08:52:53.521676+00:00|
|WETH-BRETT (aerodrome-slipstream)|$1000.00|1220.40|$134.4100|$88.2425|$66.9904|1.317242|是|reports/lp_tp_d/20260810_d4_top68_w10_normal/scanner.db @ 2026-08-10T13:24:29.678852+00:00|
|USDC-SAPIEN (aerodrome-slipstream)|$1000.00|1220.40|$103.7100|$56.8017|$81.3444|0.698287|否|reports/lp_funnel_autopsy/20260810_043427/scanner.db @ 2026-08-10T04:34:39.491608+00:00|
|VIRTUAL-USDC (uniswap-v3)|$1000.00|1220.40|$-175.7500|$6.3886|$102.2045|0.062508|否|reports/lp_scanner/scanner.db @ 2026-08-13T18:06:05.743131+00:00|

## 逐项口径（每池按绝对差异降序）

### WETH-CBBTC — 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|lvr_ev_usd|UNMODELED|$52.6076|$52.6076|N/A (paper UNMODELED)|
|reward_haircut_deduction_usd|$0.0000|$27.3074|$27.3074|N/A (paper zero)|
|entry_cost_usd|UNMODELED|$3.8076|$3.8076|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$3.8076|$3.8076|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$2.2344|$2.2344|N/A (paper UNMODELED)|
|reward_conversion_cost_usd|UNMODELED|$0.5865|$0.5865|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.0058|$0.0058|N/A (paper UNMODELED)|
|fee_ev_usd|$75.4894|$75.4894|$0.0000|1.0000×|
|reward_ev_usd|$54.6149|$54.6149|$0.0000|1.0000×|
|il_ev_usd|$105.2151|$105.2151|$0.0000|1.0000×|

### WETH-USDC — 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|reward_haircut_deduction_usd|$0.0000|$137.3132|$137.3132|N/A (paper zero)|
|lvr_ev_usd|UNMODELED|$36.1253|$36.1253|N/A (paper UNMODELED)|
|reward_conversion_cost_usd|UNMODELED|$6.3407|$6.3407|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$2.0288|$2.0288|N/A (paper UNMODELED)|
|entry_cost_usd|UNMODELED|$1.1300|$1.1300|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$1.1300|$1.1300|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.0170|$0.0170|N/A (paper UNMODELED)|
|fee_ev_usd|$845.2374|$845.2374|$0.0000|1.0000×|
|reward_ev_usd|$274.6263|$274.6263|$0.0000|1.0000×|
|il_ev_usd|$72.2507|$72.2507|$0.0000|1.0000×|

### WETH-USDC — 0x0b1c2dcbbfa744ebd3fc17ff1a96a1e1eb4b2d69

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|lvr_ev_usd|UNMODELED|$15.6208|$15.6208|N/A (paper UNMODELED)|
|entry_cost_usd|UNMODELED|$4.1516|$4.1516|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$4.1516|$4.1516|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$0.6129|$0.6129|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.0477|$0.0477|N/A (paper UNMODELED)|
|fee_ev_usd|$87.6535|$87.6535|$0.0000|1.0000×|
|reward_ev_usd|$0.0000|$0.0000|$0.0000|N/A (paper zero)|
|reward_haircut_deduction_usd|$0.0000|$0.0000|$0.0000|N/A (paper zero)|
|il_ev_usd|$31.2416|$31.2416|$0.0000|1.0000×|
|reward_conversion_cost_usd|UNMODELED|$0.0000|$0.0000|N/A (paper UNMODELED)|

### WETH-BRETT — 0x4e829f8a5213c42535ab84aa40bd4adcce9cba02

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|lvr_ev_usd|UNMODELED|$18.9322|$18.9322|N/A (paper UNMODELED)|
|reward_haircut_deduction_usd|$0.0000|$17.7989|$17.7989|N/A (paper zero)|
|reward_conversion_cost_usd|UNMODELED|$7.3529|$7.3529|N/A (paper UNMODELED)|
|entry_cost_usd|UNMODELED|$0.9766|$0.9766|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$0.9766|$0.9766|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$0.6966|$0.6966|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.1114|$0.1114|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|fee_ev_usd|$70.4436|$70.4436|$0.0000|1.0000×|
|reward_ev_usd|$35.5978|$35.5978|$0.0000|1.0000×|
|il_ev_usd|$37.8645|$37.8645|$0.0000|1.0000×|

### USDC-SAPIEN — 0x80cc08712aa61ce9dc7604f9ce7560a25094b862

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|lvr_ev_usd|UNMODELED|$24.9424|$24.9424|N/A (paper UNMODELED)|
|reward_haircut_deduction_usd|$0.0000|$12.7328|$12.7328|N/A (paper zero)|
|entry_cost_usd|UNMODELED|$2.0671|$2.0671|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$2.0671|$2.0671|N/A (paper UNMODELED)|
|reward_conversion_cost_usd|UNMODELED|$1.5734|$1.5734|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$0.6966|$0.6966|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.0335|$0.0335|N/A (paper UNMODELED)|
|fee_ev_usd|$44.0689|$44.0689|$0.0000|1.0000×|
|reward_ev_usd|$25.4657|$25.4657|$0.0000|1.0000×|
|il_ev_usd|$49.8847|$49.8847|$0.0000|1.0000×|

### VIRTUAL-USDC — 0x529d2863a1521d0b57db028168fde2e97120017c

|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|
|---|---:|---:|---:|---:|
|lvr_ev_usd|UNMODELED|$32.8481|$32.8481|N/A (paper UNMODELED)|
|entry_cost_usd|UNMODELED|$1.3699|$1.3699|N/A (paper UNMODELED)|
|exit_cost_usd|UNMODELED|$1.3699|$1.3699|N/A (paper UNMODELED)|
|exit_latency_loss_usd|UNMODELED|$0.6966|$0.6966|N/A (paper UNMODELED)|
|slippage_usd|UNMODELED|$0.1442|$0.1442|N/A (paper UNMODELED)|
|gas_usd|UNMODELED|$0.0795|$0.0795|N/A (paper UNMODELED)|
|fee_ev_usd|$6.3886|$6.3886|$0.0000|1.0000×|
|reward_ev_usd|$0.0000|$0.0000|$0.0000|N/A (paper zero)|
|reward_haircut_deduction_usd|$0.0000|$0.0000|$0.0000|N/A (paper zero)|
|il_ev_usd|$65.6962|$65.6962|$0.0000|1.0000×|
|reward_conversion_cost_usd|UNMODELED|$0.0000|$0.0000|N/A (paper UNMODELED)|

## 裁定（J1 基线）

两个仪器分歧的最大来源是 `reward_haircut_deduction_usd`，差异 $137.3132；NetCover/paper 为 N/A (paper zero)。
这里的 `UNMODELED` 不是零成本：它表示 paper runner 输出没有该项可对账成本，故不能以 paper PnL 直接证明小仓真实可执行。
