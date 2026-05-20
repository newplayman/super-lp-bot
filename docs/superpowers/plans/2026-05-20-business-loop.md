# 主业务闭环实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 scanner→pool→strategy→risk→execution 的最小业务闭环，让 shadow 模式能真正扫描池子、评估策略、创建影子仓位

**Architecture:** 采用事件驱动架构：
- Scanner 发现池子 → 写入 PoolRepo
- Strategy 从 PoolRepo 读取候选 → 评估排序
- Risk 检查 KillState/风险阈值
- Execution 创建/管理仓位（shadow 模式模拟，live 模式真实执行）
- PnL 账本记录

**Tech Stack:** Go + SQLite (初期) / PostgreSQL (生产) + Redis (可选缓存)

---

## Task 1: Scanner 写入 PoolRepo

**Files:**
- Modify: `internal/core/scanner/scanner.go`
- Modify: `internal/adapters/store/sqlite/pool_repo.go`
- Create: `internal/adapters/store/sqlite/pool_repo_test.go`

- [ ] **Step 1: 修改 Scanner.Run 让它写入 PoolRepo**

```go
func (s *defaultScanner) Run(ctx context.Context) error {
    // ... existing discovery code ...

    for _, discovery := range pools {
        pool := domain.Pool{...}
        score, _ := s.Score(ctx, pool)
        tier := s.AssignTier(score)

        // Write to PoolRepo
        err := s.poolRepo.UpsertPool(ctx, ports.PoolWithScore{
            Pool:  pool,
            Score: score,
        })
        if err != nil {
            s.log("failed to upsert pool %s: %v", pool.ID, err)
        }
    }
    return nil
}
```

- [ ] **Step 2: 给 Scanner 添加 PoolRepo 依赖**

```go
type Config struct {
    // ... existing fields ...
    PoolRepo ports.PoolRepo // 新增
}

func (s *defaultScanner) Run(ctx context.Context) error {
    // Use s.config.PoolRepo to upsert pools
}
```

- [ ] **Step 3: 在 main.go 注入 PoolRepo 到 Scanner**

```go
app.scanner = scanner.New(scanner.Config{
    Datasource: app.datasource,
    PoolRepo:   app.store.PoolRepo(), // 新增
    // ...
})
```

- [ ] **Step 4: 添加集成测试**

```go
func TestScanner_UpsertsPools(t *testing.T) {
    // 创建 mock PoolRepo
    // 调用 Scanner.Run
    // 验证 PoolRepo.UpsertPool 被调用
}
```

- [ ] **Step 5: 提交**
```bash
git add -A && git commit -m "feat: scanner writes discovered pools to PoolRepo"
```

---

## Task 2: Strategy 从 PoolRepo 读取候选

**Files:**
- Modify: `internal/core/strategy/strategy.go`
- Modify: `cmd/lpbot/main.go`

- [ ] **Step 1: 修改 Strategy 接口让 evaluateStrategies 使用真实数据**

```go
type Config struct {
    PoolRepo ports.PoolRepo // 新增
    // ...
}

func (s *defaultStrategy) evaluateStrategies(ctx context.Context) []strategy.Candidate {
    // 从 PoolRepo 读取候选池子
    pools, _ := s.config.PoolRepo.ListPools(ctx, ports.PoolFilter{
        Limit: 50,
    })

    candidates := []Candidate{}
    for _, pool := range pools {
        // 评估每个池子
        candidate := s.evaluatePool(ctx, pool)
        candidates = append(candidates, candidate)
    }

    // 排序选择
    return s.selectCandidates(candidates)
}
```

- [ ] **Step 2: 在 main.go 注入 PoolRepo 到 Strategy**

- [ ] **Step 3: 添加测试验证 Strategy 从 PoolRepo 读取**

- [ ] **Step 4: 提交**
```bash
git add -A && git commit -m "feat: strategy reads candidates from PoolRepo"
```

---

## Task 3: Risk 检查 KillState

**Files:**
- Modify: `internal/core/risk/risk.go` (检查是否存在 risk 模块)
- Modify: `cmd/lpbot/main.go`

- [ ] **Step 1: 在 evaluateStrategies 中添加 Risk 检查**

```go
func (app *App) evaluateStrategies(ctx context.Context) {
    // 获取 KillState
    killState, err := app.store.RiskRepo().GetKillState(ctx)
    if err != nil {
        app.logger.Warn("failed to get kill state", zap.Error(err))
    }

    // 如果不是 OK 级别，跳过策略执行
    if killState.Level != ports.KillLevelOK {
        app.logger.Info("kill switch active, skipping strategy",
            zap.String("level", string(killState.Level)),
            zap.String("reason", killState.Reason))
        return
    }

    // 正常执行策略...
}
```

- [ ] **Step 2: 测试 KillState 检查逻辑**

- [ ] **Step 3: 提交**
```bash
git add -A && git commit -m "feat: check kill state before strategy execution"
```

---

## Task 4: Execution 创建影子仓位

**Files:**
- Modify: `cmd/lpbot/main.go`
- Modify: `internal/core/execution/execution.go` (如果存在)

- [ ] **Step 1: 实现影子仓位创建逻辑**

```go
func (app *App) executeCandidates(candidates []strategy.Candidate) {
    for _, c := range candidates {
        if c.Score.Total < 60 { // 最低分数门槛
            continue
        }

        // 创建影子仓位（不实际发送交易）
        pos := &domain.Position{
            ID:        generatePositionID(),
            Chain:     c.Pool.Chain,
            PoolID:    c.Pool.ID,
            Status:    domain.StatusIntended,
            Tier:      c.Pool.Tier_,
            AmountUSD: domain.MustDecimal("100"), // 影子仓位固定金额
            TickLower: c.TickLower,
            TickUpper: c.TickUpper,
            OpenedAt:  time.Now().UnixMilli(),
        }

        // 保存到 PositionRepo
        err := app.store.PositionRepo().Save(ctx, pos)
        if err != nil {
            app.logger.Warn("failed to save shadow position", zap.Error(err))
        }

        app.logger.Info("created shadow position",
            zap.String("pool", c.Pool.ID),
            zap.Float64("score", c.Score.Total))
    }
}
```

- [ ] **Step 2: 测试影子仓位创建**

- [ ] **Step 3: 提交**
```bash
git add -A && git commit -m "feat: create shadow positions for evaluated candidates"
```

---

## Task 5: PnL 账本记录

**Files:**
- Modify: `cmd/lpbot/main.go`

- [ ] **Step 1: 在策略执行后记录 PnL 条目**

```go
func (app *App) recordStrategyEntry(candidate strategy.Candidate, action string) {
    entry := ports.LedgerEntry{
        ID:         generateLedgerID(),
        PositionID: candidate.PositionID,
        Kind:       ports.LedgerEntrySwap,
        Amount:     domain.ZeroDecimal, // 影子仓位无实际盈亏
        TokenSymbol: "USDC",
        TxHash:     "shadow_" + action,
    }

    _, err := app.store.LedgerRepo().Append(ctx, entry)
    if err != nil {
        app.logger.Warn("failed to record ledger entry", zap.Error(err))
    }
}
```

- [ ] **Step 2: 提交**
```bash
git add -A && git commit -m "feat: record PnL ledger entries for strategy actions"
```

---

## Task 6: 集成测试

**Files:**
- Create: `tests/integration/business_loop_test.go`

- [ ] **Step 1: 创建端到端测试**

```go
func TestBusinessLoop_Shadow(t *testing.T) {
    // 启动应用
    app := setupTestApp(t)

    // 触发一次扫描
    app.scanner.Run(context.Background())

    // 验证池子被写入
    pools, _ := app.store.PoolRepo().ListPools(ctx, ports.PoolFilter{Limit: 10})
    assert.Greater(t, len(pools), 0)

    // 触发策略评估
    app.strategy.Run(context.Background())

    // 验证影子仓位被创建
    positions, _ := app.store.PositionRepo().FindByChainAndStatus(
        ctx, domain.ChainBase, domain.StatusIntended)
    assert.Greater(t, len(positions), 0)
}
```

- [ ] **Step 2: 提交**
```bash
git add -A && git commit -m "test: add business loop integration tests"
```

---

## Task 7: VPS 部署配置

**Files:**
- Create: `configs/config.vps.toml`
- Modify: `docker-compose.yml` (添加 PostgreSQL + Redis)

- [ ] **Step 1: 创建 VPS 配置文件**

```toml
[store]
backend = "postgres"
postgres_url = "postgres://postgres:password@localhost:5432/lpbot_shadow?sslmode=disable"

[platform]
log_level = "debug"
```

- [ ] **Step 2: 添加 Docker Compose 配置**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: lpbot_shadow
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"
```

- [ ] **Step 3: 提交**
```bash
git add -A && git commit -m "chore: add VPS deployment config and docker-compose"
```

---

## 执行后验证

在 VPS 上执行：
```bash
# 1. 拉取最新代码
git pull origin main

# 2. 启动 PostgreSQL
docker-compose up -d postgres

# 3. 构建 shadow 版本
go build -tags shadow -o lpbot_shadow ./cmd/lpbot

# 4. 运行
./lpbot_shadow -config configs/config.vps.toml

# 5. 检查日志
# 应该看到：
# - Scanner 发现池子
# - Pools 写入数据库
# - Strategy 评估候选
# - Shadow positions 创建
```

---

## Self-Review Checklist

- [ ] Scanner 发现池子后写入 PoolRepo
- [ ] Strategy 从 PoolRepo 读取而非模拟数据
- [ ] Risk 检查 KillState 并阻止危险级别执行
- [ ] Execution 创建影子仓位（不实际发送交易）
- [ ] Ledger 记录策略操作
- [ ] 集成测试覆盖完整流程
- [ ] VPS 配置文件正确