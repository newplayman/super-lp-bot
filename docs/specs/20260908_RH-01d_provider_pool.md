# RH-01d：多提供方轮循池与逐方法可用性核验（解 LIVE 闸的单点阻塞）

## 背景

PRD §8.3 要求 `usable_provider_count >= 2` 才允许 LIVE。当前实测只有 1 个可用后端，**LIVE 闸因此一直 BLOCKED**，这是与经济结论无关的纯工程阻塞。用户已授权「免费公开 RPC 只读探测，并可用多个免费节点做轮循池」。

本包只做**离线纯逻辑**：所有网络调用通过注入的 `call_fn` 完成，模块自身不联网。主脑负责拿真实端点跑核验。

## 只写两个文件（写到 `/tmp/codex_out/RH-01d/` 下同名子目录）

1. `scripts/lp_rh_provider_pool_v1_readonly.py`（≤320 行）

   - `verify_provider_methods(providers, methods, call_fn) -> dict`
     `providers` 是 `[{"name","url"}]`，`methods` 是 `[{"method","params"}]`。
     `call_fn(url, method, params)` 返回结果或抛异常。逐 (provider, method) 记录
     `{"ok": bool, "latency_ms": float|None, "error": str|None, "result_digest": str|None}`。
     `result_digest` 用 `sha256(json.dumps(result, sort_keys=True))[:16]`。
     **一个方法失败不得影响同提供方的其他方法**，也不得中断整个矩阵。
   - `usable_providers(matrix, required_methods) -> list[str]`
     只有**全部** `required_methods` 都 `ok` 的提供方才算可用。少一个方法就不算——
     「大部分方法能用」在 fail-closed 语义下等于不可用。
   - `detect_disagreement(matrix, methods, *, consensus_methods) -> list[dict]`
     对 `consensus_methods`（如 `eth_chainId`、同一 `blockNumber` 的 `eth_call`）比较各提供方的
     `result_digest`。不一致返回 `[{"method","digests":{name:digest}}]`。
     **禁止取平均、取多数、或静默选第一个**——返回分歧清单交上层判 `SOURCE_DISAGREEMENT`。
   - `class ProviderPool`：轮循 + 故障隔离
     - `__init__(providers, *, cooldown_base=2.0, max_backoff_exponent=30)`
     - `pick() -> Optional[dict]`：轮循返回当前**未处于冷却**的提供方；全在冷却返回 `None`（**不许硬选一个**）。
     - `report_failure(name, now)` / `report_success(name)`：失败计数递增，冷却
       `cooldown_base ** min(fails - 1, max_backoff_exponent)` 秒。
       **`min(..., 30)` 封顶是硬要求**：本仓 `lp_rpc_pool_v1_readonly.py:280` 曾因
       `2**(fails-1)` 在 `fails>=1025` 时 float 溢出，让一个跑了 28 天的守护进程 100% 的行带
       OverflowError。成功后计数清零。
     - `health() -> dict`：每个提供方的 `fails` / `cooling_until` / `last_ok`。
   - `live_readiness(usable_count, *, min_required=2) -> dict`
     返回 `{"status": "PASS"|"BLOCKED", "reason": None|"SINGLE_PROVIDER"|"NO_PROVIDER", "usable_count": int}`。
     `min_required` 默认 2，**函数内不得把它下调**。
   - `main()`：`--providers-json --methods-json --out`，网络调用走 `call_fn` 默认实现（urllib，
     带 `User-Agent`），但 `--dry-run` 时用假 `call_fn` 不联网。

2. `tests/test_lp_rh_provider_pool_v1_readonly.py`（≤300 行，**≥20 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。全部用假 `call_fn`，**不许联网**。必测：
   - 3 提供方 × 4 方法全 ok → `usable_providers` 返回 3 个。
   - 某提供方缺 1 个方法 → **不在** `usable_providers` 里（断言不在列表中）。
   - 某方法抛异常不影响同提供方其他方法的 `ok`（矩阵仍是 3×4 完整）。
   - `detect_disagreement`：两方 digest 相同、第三方不同 → 返回 1 条，且 `digests` 含全部三方。
   - 全部一致 → 返回空列表。
   - **退避封顶**：`report_failure` 调用 5000 次后 `cooling_until` 是有限浮点数（`math.isfinite`），
     且不抛 `OverflowError`。**这条是本包核心，直接对应本仓真实故障。**
   - `report_success` 后 `fails` 归零、立即可被 `pick` 选中。
   - 全部提供方冷却中 → `pick()` 返回 `None`（用 `is None` 断言，不许退化成选第一个）。
   - 轮循公平性：6 次 `pick` 在 3 个健康提供方上各出现 2 次。
   - `live_readiness(1)` → `BLOCKED` / `SINGLE_PROVIDER`；`live_readiness(0)` → `BLOCKED` / `NO_PROVIDER`；
     `live_readiness(2)` → `PASS`。
   - `live_readiness(1, min_required=1)` 显式传参才 PASS——证明默认值没被内部改写。

## 硬约束
不读、不改 `/opt/lpbot` 下任何文件（spec 除外）。测试不得发起真实网络请求。单次写 ≤120 行。写完 `ast.parse` 自检。

## 验收
```
cd /tmp/codex_out/RH-01d && PYTHONPATH=/opt/lpbot/lp-bot-v3-origin-check:/tmp/codex_out/RH-01d \
  /root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
必须真跑通、全绿、≥20 passed，贴尾部 15 行。
