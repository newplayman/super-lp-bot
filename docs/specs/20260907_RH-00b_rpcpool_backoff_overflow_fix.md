# RH-00b：修复 RpcPool 指数退避 float 溢出（最小改动 + 配对测试）

## 背景（一段）

`scripts/lp_rpc_pool_v1_readonly.py:280` 的 `backoff = self._cooldown_base * (2 ** (fails - 1))` 在某端点连续失败 `fails >= 1025` 时抛 `OverflowError: int too large to convert to float`（`_fails` 只在成功时清零，长跑 daemon 必然累积）。`RpcPool.call` 的 except 分支里第二次 `_penalize`（:371）不在 try 内，异常穿透到调用方，被 `lp_pool_resolve_and_rank_v1_readonly.py` 记成探针错误 → `factory_registry_probe_incomplete` → 池被永久 fail-closed。迁移库证据：2026-08-31 起 100% 该原因的行都带 OverflowError。详见 `reports/rh_pivot/20260907T124500Z/RH-00/LEGACY_FAILURE_AUTOPSY.json`。

## 改哪些文件、改成什么

1. `scripts/lp_rpc_pool_v1_readonly.py`，只改 `_penalize`（约 :277-281）：把指数封顶，例如
   ```python
   exponent = min(fails - 1, 30)
   backoff = self._cooldown_base * (2 ** exponent)
   self._cooldown_until[url] = self._clock.now() + min(backoff, self._cooldown_max)
   ```
   `fails` 计数本身继续累加（`health_snapshot` 的 `consecutive_failures` 语义不变）。不改 `_cooldown_max` 默认值、不改 `_reset`、不改 `call` 的其它逻辑。
2. `tests/test_lp_rpc_pool_v1_readonly.py`：追加 2 个测试（放文件末尾，不改已有测试）：
   - `test_penalize_does_not_overflow_after_many_failures`：构造 `RpcPool(chain="base", clock=<固定时钟>)`（看文件里已有的 fake clock / 构造方式，照抄），把 `pool._fails[url]` 设为 `1024`、`5000`，调用 `pool._penalize(url)` 不抛异常，且 `pool._cooldown_until[url] == clock.now() + pool._cooldown_max`。
   - `test_call_survives_endpoint_with_overflow_level_failures`：用已有的 fake `post` 让某端点持续失败，预置该端点 `_fails=2000`，调用 `pool.call(...)`，断言得到的是 `RpcPoolExhaustedError`（或成功回退到其它健康端点），**不是** `OverflowError`。
3. 不新增文件。

## 不许动什么

- 不动六常量文件、NetCover 引擎、成本模型、任何阈值。
- 不动 `.gitignore`、不动 `scripts/lp_rpc_pool_v1_readonly.py` 里现有未提交的 `health_snapshot` `endpoints` 改动（保留原样，不要"顺手"提交或回退）。
- 不删/不改已有测试；不重构；不格式化无关行。
- 不启动任何 daemon，不联网，不读 `.env*`。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件（该文件 511 行，用 `sed -n` 取片段）。

## 验收标准（逐条可判定）

- [ ] `git diff --stat` 只含 `scripts/lp_rpc_pool_v1_readonly.py` 与 `tests/test_lp_rpc_pool_v1_readonly.py`。
- [ ] `_penalize` 在 `fails=1025` 与 `fails=5000` 时不抛异常，cooldown 等于 `_cooldown_max` 上限。
- [ ] 上述两个新测试通过；`tests/test_lp_rpc_pool_v1_readonly.py` 全部通过。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider` 结果为 `3111 passed, 14 skipped`（3109 + 新增 2），0 failed。
- [ ] 六常量 grep 输出与 `reports/rh_pivot/20260907T124500Z/RH-00/BASELINE_RAW.log` 中一致。

## 验证命令（在仓库根目录 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rpc_pool_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
/root/lp-bot/.venv/bin/python -c "import sys;sys.path.insert(0,'.');from scripts.lp_rpc_pool_v1_readonly import RpcPool;p=RpcPool(chain='base');u=p._endpoints[0]['url'];p._fails[u]=4999;p._penalize(u);print('ok',p._fails[u])"
git diff --stat
```
