# Phase 0 测试报告

**日期:** 2026-05-19
**Commit:** 2053a8a

## 测试覆盖

### 1. 单元测试 (`make test`)

| 状态 | 包数 | 说明 |
|------|------|------|
| ✅ PASS | 45 | 所有包通过 |
| ⏭ SKIP | 12 | 无测试文件（正常） |

### 2. 属性测试 (`make test-property`)

| 状态 | 包数 | 说明 |
|------|------|------|
| ✅ PASS | 45 | 包含 PnL、IL、TickMath 属性测试 |

### 3. 回归测试 (`make build-dryrun`)

| 状态 | 测试 | 说明 |
|------|------|------|
| ✅ PASS | `./bin/lpbot-dryrun --help` | CLI 正常启动 |
| ✅ PASS | `./bin/lpbot-backtest --version` | 版本 0.0.1-phase0 |

### 4. 功能测试 (backtest CLI)

| 场景 | 状态 | 输出 |
|------|------|------|
| 无缓存模式 | ✅ | 288 swaps, 24 pool states |
| 有缓存模式 | ✅ | 288 swaps (从 cache 读取) |
| 输出文件 | ✅ | verdict.md, summary.json, pnl_series.csv |
| Cache DB schema | ✅ | cache_swaps, cache_pool_states |

### 5. 已知限制

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Verdict FAIL | Phase 0 无 ground truth | Phase 1 接入 DexScreener API |
| 所有 pools 显示 FAIL | fixture 数据无对比基准 | Phase 1 使用真实池数据 |

## 缓存一致性验证

Cache schema 与 loader 查询一致（2026-05-19 修复）:

```sql
-- cache_swaps 表结构
(id, pool_id, chain, timestamp, block_number,
 amount0, amount1, trader, tick, sqrt_price_x96)

-- cache_pool_states 表结构
(id, pool_id, block_number, block_hash, block_time,
 tick, liquidity, reserve0, reserve1, sqrt_price_x96, fee_growth_0, fee_growth_1)
```

## 快速验证命令

```bash
# 完整测试
make test-all

# Backtest 功能验证
./bin/lpbot-backtest \
  --pool=0xMockPool123 \
  --chain=base \
  --from=2024-01-01T00:00:00Z \
  --to=2024-01-02T00:00:00Z \
  --output=/tmp/verify
```

## 下一步 (Phase 1)

1. 接入 DexScreener API 获取真实 swap 数据
2. 接入 GeckoTerminal 获取历史价格
3. 验证 ground truth 对比精度 < 5%