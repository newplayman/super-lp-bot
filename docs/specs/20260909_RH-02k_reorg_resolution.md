# RH-02k：把分歧检测接到回滚上——但先解决「哪个 hash 是孤块」

## 为什么这一项可以接线，而另五项不可以

今晚建成六项闸门能力，其中五项（gas sanity、native 储备、空区间、
regime confidence、MEME 聚合）都在改变**「什么情况下允许开仓」**，
那是用户的资金政策决定，主脑不接。

**重组回滚不同**：它作废基于被弃链的派生数据，**永远不会放进任何新东西**，
只会让已有结论失效。纯正确性改进，不触及许可边界，因此可以接。

## 但天真的接线是错的

`scripts/lp_rh_capabilities_v1_readonly.py:249` 检出分歧时返回

```python
{"independent": None, "reason": "BLOCK_HASH_DIVERGENCE"}
```

**它不说哪个 hash 是孤块。** 两个提供方在同一高度报不同 hash 时，
单凭这一刻的信息**无法判断哪条是规范链**——直接调
`apply_rollback(orphaned_block_hash=...)` 等于随便选一个回滚，
可能作废的是正确数据。

**必须先有确认步骤。**

## 只写一个文件 + 其测试

1. `scripts/lp_rh_reorg_resolution_v1_readonly.py`（≤260 行）
   复用 `scripts.lp_rh_reorg_rollback_v1_readonly` 的
   `plan_rollback` / `apply_rollback`，**不要重写**。

   - 新表（幂等 `CREATE TABLE IF NOT EXISTS`）
     `rh_reorg_contested`：`block_number, hash_a, hash_b, first_seen_at,
     resolved_at, canonical_hash, orphaned_hash, status`，
     主键 `(block_number, hash_a, hash_b)`。
     `status` ∈ `CONTESTED` / `RESOLVED` / `UNRESOLVABLE`。
   - `record_contested(conn, *, block_number, hash_a, hash_b, now)`
     检出分歧时登记。**此时不回滚**，`status="CONTESTED"`。
     同一组合重复登记只有一行（幂等）。
   - `resolve_contested(conn, *, block_number, canonical_hash_fn, now, min_depth=64)`
     `canonical_hash_fn(block_number) -> str | None`，由调用方注入
     （真实实现是向链头已推进 ≥`min_depth` 后重查该高度的 hash）。
     - 返回的 hash 等于 `hash_a` → `orphaned_hash = hash_b`，反之亦然，
       `status="RESOLVED"`。
     - 返回 `None`（查不到）→ 保持 `CONTESTED`，**不要猜**。
     - 返回的 hash **两个都不等于** → `status="UNRESOLVABLE"`，
       `orphaned_hash` 为 `None`，并在返回值里点明——
       **这说明两个提供方都错了或发生了多次重组，不能据此回滚任何一方。**
   - `apply_resolved_rollbacks(conn, *, now) -> dict`
     对所有 `status="RESOLVED"` 且尚未回滚的行，调 `apply_rollback`
     作废 `orphaned_hash` 的派生行。返回
     `{"resolved_count", "rolled_back": {...}, "undecidable_tables": [...]}`。
     **`UNRESOLVABLE` 与 `CONTESTED` 一律不回滚。**
   - `main()`：`--db --block-number --hash-a --hash-b` 登记；
     `--resolve --block-number` 解析；`--apply` 执行已解析的回滚。
     **三个动作必须显式给出，默认什么都不做。**

2. `tests/test_lp_rh_reorg_resolution_v1_readonly.py`（≤240 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite + 注入的假 `canonical_hash_fn`，不许联网。** 必测：
   - 登记后 `status == "CONTESTED"` 且**未发生任何回滚**
     （断言派生表的 `invalidated_by_block` 仍全为 NULL）。
   - 同一组合登记两次只有一行。
   - `canonical_hash_fn` 返回 `hash_a` → `orphaned_hash == hash_b`，
     `status == "RESOLVED"`。
   - 返回 `hash_b` → 反向，同样正确。
   - **★返回 `None` → 保持 `CONTESTED`，`orphaned_hash is None`，不回滚★**
     （查不到就不猜）。
   - **★返回第三个 hash → `UNRESOLVABLE`，`orphaned_hash is None`，不回滚★**
     （两个提供方都错了，不能据此作废任何一方）。
   - `apply_resolved_rollbacks` 只回滚 `RESOLVED` 的行：
     构造 CONTESTED / UNRESOLVABLE / RESOLVED 三行，断言只有第三行对应的
     派生行被标记。
   - 回滚后 `invalidated_by_block == orphaned_hash`。
   - **绝不删除**：回滚前后派生表 `COUNT(*)` 相同。
   - 幂等：连续两次 `apply_resolved_rollbacks`，第二次 `rolled_back` 总数为 0。
   - `undecidable_tables` 在有表无溯源时非空且传递上来。
   - `min_depth` 未达到时（注入的 `canonical_hash_fn` 返回 `None` 模拟）保持 CONTESTED。
   - `main` 不带任何动作标志时**什么都不做**且返回 0（断言库未变）。
   - 新表幂等建表：连续两次不报错。

## 不许动
不改 `lp_rh_capabilities_v1_readonly.py`（检测端不动，本包只做下游）。
不改回滚模块。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_reorg_resolution_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
