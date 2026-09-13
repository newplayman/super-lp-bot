# W4 SPEC — 修两个 Go 根因（main agent 直做）

**目标 SHA**: 18a8f39744af2d61d16737b7311d88cd88accea9

## F1: 修 Dexscreener 重复 json tag

文件：`internal/adapters/datasource/dexscreener/client.go:43-44`

```go
PoolID      string      `json:"pairAddress"`
PoolAddress string      `json:"pairAddress"`
```

修复方向：
- `PoolID` 是公开字段，删除其 json tag → `json:"-"`（不导出该字段，因为 PoolAddress 已对外）
- 保留 `PoolAddress string \`json:"pairAddress"\`` 作为 DexScreener 实际 API 字段

**先核对真实 API 语义**：
- DexScreener `/dex/tokens/{tokenAddress}` 或 `/latest/dex/pairs/{chainId}/{pairId}` 返回 `pairAddress` 字段
- `PoolID` 和 `PoolAddress` 在本仓库内是别名；PoolAddress 才是外部输入
- 不改语义，只去除冗余 json tag

**约束**：
- 只改这两行
- 不改 PoolInfo struct 其他字段
- 不改任何 PoolID 引用代码（若引用了，按需要补 json 标签为 `json:"pairAddress"` 但需修名字重复——否则用 PoolAddress）

## F2: 修 quality-gate golangci-lint 版本固定

文件：`.github/workflows/ci.yml:30` 和 `:21`

当前：
```yaml
go-version: "1.25"  # line 21
version: latest     # line 30 → 实际拉到 v1.64.8 (build go1.24 < target 1.25.7)
```

修复：
- line 30: `version: v1.65.0`（v1.65.0 built with go1.25，匹配 target）
- 备选：`v1.66.0`（最新稳定）

## F3: 修 advisory-audit govulncheck 自动切换

文件：`.github/workflows/ci.yml:71`

当前：
```yaml
- name: Install advisory tools
  run: go install golang.org/x/vuln/cmd/govulncheck@latest  # 自动切到 go1.26.8
```

修复：
- 改为 `go install golang.org/x/vuln/cmd/govulncheck@v1.1.4`（最后支持 go1.25 的版本）
- 在 advisory 步骤加 `go-version: "1.25"` 显式声明（防止自动切换）

## F4: 清理 CI 注入的空 DATABASE_URL/RH_RPC_*（保留生产 no-send 护栏）

文件：`.github/workflows/ci.yml:130-147`

当前：
```yaml
- name: Run RH Python unit + integration tests
  env:
    RH_RPC_PRIMARY: ""
    RH_RPC_SECONDARY: ""
    DATABASE_URL: ""
  run: |
    cd ${{ github.workspace }}
    python -m pytest tests/ -q --tb=short -p no:cacheprovider
- name: Run daemon entry-point integration subset
  env:
    RH_RPC_PRIMARY: ""
    RH_RPC_SECONDARY: ""
  run: |
    cd ${{ github.workspace }}
    python -m pytest tests/ -q -k "episode_persisted or daemon or reconciliation or graduation or readiness" \
      --tb=short -p no:cacheprovider
```

**问题**：空字符串注入触发 200 个 no-send 测试（生产护栏按设计拒绝）。这些 fail 是预期行为，但被 pytest 报告为 fail，导致 415 CI fail 中 200 是 no-send 护栏正确触发的副作用。

**修复**：
- 在第一个 step（unit + integration）**不**注入空 env（让测试用默认 fake transport / tmp_path SQLite）
- 仅在第二个 step（daemon entry-point）保留空 env（验证 no-send 真的拦截）
- 在 README/CI 注释里说明：单元测试必须在没有 DB/RPC 的情况下自洽

## F5: 修硬编码路径 /opt/lpbot/lp-bot-v3-origin-check

CI_VERIFIED_EXCERPTS 提到 80 fail 涉及硬编码该路径。修复：
- 找出所有引用 `/opt/lpbot/lp-bot-v3-origin-check` 的测试代码
- 替换为 `Path(__file__).resolve().parent.parent` 或 `os.environ.get("LPBOT_REPO_ROOT", os.getcwd())`
- 优先级：先看 FAILURE_INVENTORY.json 哪 80 个；如果不能精确查，先 grep -r "/opt/lpbot/lp-bot-v3-origin-check" tests/ 看哪些文件命中

## 验收命令

```bash
# 1. Go fix 后不能引入新 Go vet 错
cd /opt/lpbot/lp-bot-v3-origin-check
go mod tidy && git diff --exit-code go.mod go.sum
go vet ./... 2>&1 | tee /tmp/w4_govet.out
# 期望：无 output
# 2. YAML 解析正确
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"
# 3. pytest 不引入新 fail
python -m pytest tests/ -q --tb=line -p no:cacheprovider --junitxml=/tmp/w4_junit.xml 2>&1 | tail -10
# 期望：fail ≤ V2 baseline 53（最好少因 no-send 修复减至 53 - 200 + something）
```

## 边界

- 不改任何 *_test.go（CLAUDE.md CI 不变量）
- 不动 main 分支
- 不引入新依赖
- 不降 Go 版本
- 不 continue-on-error（CLAUDE.md 不允许）
- 不批量 skip/deselect
