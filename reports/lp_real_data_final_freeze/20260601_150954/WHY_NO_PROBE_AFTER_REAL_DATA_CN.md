# 为什么当前不能 Probe

- `can_run_probe_now = false`
- `can_reopen_probe_preflight = false`
- `strict_probe_readiness_pass = false`
- `edge_proven = no`
- `tiny_canary_allowed = no`

原因：

- probe 可以在未来创建真实 tokenId，但 probe 不是为了“补证据就直接下场”。
- 当前没有 actual fee positive 证据。
- 当前 6 个 positive proxy 全部来自 pool-level / simulated fee。
- 这些信号不满足 strict probe readiness，也不足以支持进入 preflight。
- 因此不能把“想拿 tokenId”当成当前直接 probe 的理由。

