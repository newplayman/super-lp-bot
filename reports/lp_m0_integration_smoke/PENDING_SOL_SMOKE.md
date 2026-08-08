# M0 integration smoke — PENDING_SOL_SMOKE

本文件是验收官 gpt-5.6-sol 的真实输出承载位置。Luna 未执行、未伪造任何全链路结果。

## Required chain

1. `scanner daemon --once --vetted-menu-out ...`：保留 screened/resolved/scored/accepted 原始 stdout；accepted=0 也是有效真实事实。
2. 仅把 `scanner_evidence_origin=live_opportunity_scores` 的记录称为 live vetted；若 accepted=0，可用显式 `fixture_only_not_live_vetted` 的审计 fixture 验证 bridge/allocator 机械链路，但两类证据必须分开。
3. allocator 必须显示 NetCover、PositionCap、absolute-profit gate 结果。
4. Base 真实池 paper runner 1 tick：保留 heartbeat/final_state，核对三口径、exit state、23 字段、`portfolio_nav_usd`、`fee_prediction_usd`、scanner.db gate row。
5. Solana：经 WP01 RpcPool 做真实 `getSlot` + `getAccountInfo`。当前 runner swap decoder 是 EVM-only，除非另有已验收 connector，不得将该探活称为完整 LP tick。

## SOL output

`PENDING_SOL_SMOKE`
