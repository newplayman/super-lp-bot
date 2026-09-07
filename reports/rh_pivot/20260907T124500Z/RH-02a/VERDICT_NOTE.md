# RH-02a 主脑裁决：ACCEPT

`qwen-review` 结论 ACCEPT，五条验收标准实测通过。主脑独立复核（不依赖 worker 自报）：

| 检查 | 结果 |
|---|---|
| 16 张 `rh_*` 表建成 | 是（`--init` 输出逐一列出） |
| `PRAGMA user_version` | 1 |
| `journal_mode` / `foreign_keys` | `wal` / `1` |
| 新测试 | 24 passed |
| 全量 pytest | **3174 passed / 14 skipped / 0 failed**（3150 + 24 精确吻合） |
| DDL 禁用类型 | `REAL`/`NUMERIC`/`TIMESTAMPTZ`/`UUID`/`SERIAL` 在 DDL 中零命中（仅出现在错误消息字符串里） |
| 浮点金额 | `assert_decimal_text(1.5)` → `TypeError: REAL_NOT_ALLOWED_FOR_MONEY` |
| uint256 十进制串 | 2^256-1 全长 78 位字符串接受 |
| 缺输入 | `assert_decimal_text(None)` 返回 `None`，不填 0 |
| 非 UTC 时间 | `2026-09-07 12:00:00` 与 `+02:00` 均抛 `NON_UTC_TIMESTAMP` |
| **T11 reorg 前提** | 同 `block_number` 不同 `block_hash` 的两行可共存（2 rows）；完全相同的四元组抛 `IntegrityError` |
| **账本幂等** | 重复 `idempotency_key` 抛 `IntegrityError` |
| tracked diff | 空 |

## 已知限制（不阻塞，RH-02b 处理）

1. `migrate()` 用 `executescript`（`scripts/lp_rh_store_v1_readonly.py:211`），会隐式提交调用方的未决事务。实测确认。DDL 自身仍是原子的（`BEGIN…COMMIT` 包裹）。由于 `migrate` 只在初始化时对全新连接调用，实际使用不受影响。**RH-02b 加一行防御断言**：`migrate` 入口若 `conn.in_transaction` 为真则抛错。
2. 只读 URI `file:{path}?mode=ro` 对含 `?` 或空格的路径不健壮。本项目路径不含这些字符，暂不处理。

**裁决：ACCEPT。**
