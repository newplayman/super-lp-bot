# 为什么当前不允许 probe

结论先行：

- `can_run_probe_now = false`
- `manual approval required for probe = true`
- 但即使有人工批准，当前也不建议继续 probe。

理由：

1. `positive_proxy_count = 0`
2. `positive_proxy_count_fixed_cost_0 = 0`
3. `positive_proxy_count_zero_il_lvr = 0`
4. `probe_candidate_count = 0`
5. `edge_proven = no`
6. `tiny_canary_allowed = no`

probe 的原始用途：

- `10U / 20U probe` 本来只是做通道验证和小规模 preflight。

为什么现在连 probe preflight 都不建议：

- 现在不是“候选池已有正 proxy，只差通道确认”。
- 现在是“连 economics proxy 都没有候选池”。
- 因此 probe 不会帮助验证 edge，只会把没有正向证据的假设推进到更靠近执行的一层。

当前边界：

- 不 probe
- 不 canary
- 不 live
