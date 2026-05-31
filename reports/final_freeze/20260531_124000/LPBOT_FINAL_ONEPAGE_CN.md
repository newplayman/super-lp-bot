# LPBOT 最终一页总结

最终结论：当前 LP 研究线应停止，不做 canary，不做 micro-live。

为什么停：
- 主策略 current_full_strategy 失败。
- fixed horizon 和 intent lifecycle 都没形成可实用 proof。
- Tier B 没有可推进候选，Tier C 批次已 reject。
- Risk-Aware Short-Hold 证明 quarantine 有帮助，但 risk-exit 本身没用。
- Pool Regime 方向修掉 leakage 之后，tail 虽改善，但机会保留率太低。
- Fee Velocity / Exit Depth 最终也没有任何 practical variant 通过 gate。

已经试过什么：
- position lifecycle proof
- fixed horizon / intent lifecycle
- regime-aware short-hold
- fee / depth / slippage / small-cap variants

最大教训：
- 先冻结 proof unit，再跑研究。
- 先防 lookahead 和重复计数，再谈 edge。
- 只会压 tail 但不能保留机会的过滤器，不等于策略。

未来怎么重启：
- 先补新数据源，尤其是 fee accrual、exit depth、holder/trader、高频 entry-safe snapshots。
- 然后重新开题，不要继续同一批参数搜索。

当前是否能 canary：不能。
