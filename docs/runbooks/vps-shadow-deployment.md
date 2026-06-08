# VPS Shadow Deployment Runbook

> 基于 `feat/supabase-postgres-deployment` 分支的 Shadow 部署 runbook

目标：统一本地与 VPS 的仓库来源、分支与配置入口，避免因为目录名差异/手工 `.env` 覆盖造成数据库混淆，并为后续 canary/live 保留统一入口。

## 1. 仓库与分支

- Git 仓库：`git@github.com:newplayman/super-lp-bot.git`
- 分支：`feat/supabase-postgres-deployment`（数据库改造期间固定）
- VPS 产物不直接使用本地 `.env` 文件，全部通过环境变量注入。

## 2. VPS 标准目录（不再保留旧名）

```bash
export LPBOT_ROOT=/opt/lpbot/lp-bot-v3
```

如果出现历史错误目录，先清理：

```bash
sudo rm -rf /opt/lpbot/lp-bot-mvp /opt/lpbot/v3 /opt/lpbot/lp-bot 2>/dev/null || true
```

## 3. 首次部署

```bash
ssh -i ~/.ssh/lpbot_ed25519 lpbot@157.173.123.24

mkdir -p /opt/lpbot
cd /opt/lpbot
git clone git@github.com:newplayman/super-lp-bot.git $(basename "$LPBOT_ROOT")
cd "$LPBOT_ROOT"
git checkout feat/supabase-postgres-deployment
git pull origin feat/supabase-postgres-deployment
make build-shadow
```

## 4. 配置文件与环境变量

- `configs/config.shadow.toml` 和 `configs/config.vps.toml` 使用 `${VAR}` 占位符读取环境变量（不写死密码）。
- 可选变量在 config 中用 `${VAR:-}` 兜底（缺省空字符串），不会因环境变量缺失而 panic。
- `.env` 类文件不入库，只作为启动环境注入。

初始化 shadow 实例文件：

```bash
cd "$LPBOT_ROOT"
cp .env.example .env
cp .env.postgres.example .env.postgres
cp .env.redis.example .env.redis
cp .env.dashboard.example .env.dashboard
cp .env.alerting.example .env.alerting
chmod 600 .env .env.postgres .env.redis .env.dashboard .env.alerting
```

按实际值编辑：

```bash
vim .env
vim .env.postgres
vim .env.redis   # 可选；缺省 redis://127.0.0.1:6379/0
vim .env.dashboard   # 可选；缺省空 token（dashboard 端点拒绝未授权）
vim .env.alerting    # 可选；缺省空 token（alerting 静默关闭）
```

推荐变量：

- `BASE_RPC_PRIMARY`, `BASE_RPC_FALLBACK`, `BASE_WS`, `SOL_RPC_PRIMARY`（可空，缺省 shadow 仍启动）
- `DATABASE_URL` 或 `POSTGRES_DSN`（VPS 连接 `vps` 上 PostgreSQL 的连接串，**shadow 必需**）
- `REDIS_URL`（可选，缺省 redis://127.0.0.1:6379/0）

## 4.1 Canary / Live 变量入口

- QuickNode Base RPC：
  - `BASE_RPC_PRIMARY`
  - `BASE_WS`
- OKX Onchain：
  - `OKX_API_KEY`
  - `OKX_API_SECRET`
  - `OKX_API_PASSPHRASE`
  - `OKX_PROJECT_ID`
- 钱包地址：
  - `CANARY_WALLET_ADDRESS`
  - `LIVE_WALLET_ADDRESS`

推荐直接从仓库模板生成：

```bash
cp .env.canary.example .env.canary
cp .env.live.example .env.live
chmod 600 .env.canary .env.live
```

说明：
- `configs/config.canary.toml` 默认 `execution.backend = "native-rpc"`，只需要 QuickNode/RPC 即可。
- 若后续切换 `execution.backend = "okx-onchain"`，再填写 OKX 变量；当前代码只做配置门禁与 readiness 展示，不代表已经完成真实交易执行。
- `POSTGRES_DSN` 如果未单独填写，会自动回退到 `.env.postgres` 里的 `DATABASE_URL`。
- **当前 canary/live 服务仍 LOCKED**（参考 `reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/FINAL_PAUSE_VERDICT.json`）。本 runbook 仅描述部署预备，不授权启动 canary/live。

## 4.2 Postgres 迁移入口

使用 `scripts/migrate-postgres.sh`（推荐）或 `make migrate-postgres`：

```bash
# Plan（只列要 apply 的文件，不执行）
make migrate-postgres-plan

# Status（验表存在性）
make migrate-postgres-status

# Apply（实际 apply）
make migrate-postgres
```

DSN 解析顺序：`POSTGRES_DSN` > `DATABASE_URL` > 自动加载的 `.env.postgres` / `.env.canary`。

防止误连生产：DSN 包含 `supabase.co` / `rds.amazonaws.com` / `prod` / `production` 时，脚本拒绝执行，需设置 `LPBOT_MIGRATE_ALLOW_LIVE=YES` 显式 override。

## 5. 安装依赖与数据库

```bash
sudo apt-get update
sudo apt-get install -y postgresql redis-server
```

推荐先确认 Redis 本机可达：

```bash
redis-cli ping
# 期望: PONG
```

```bash
sudo -u postgres psql -c "CREATE USER lpbot WITH LOGIN PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE lpbot_shadow OWNER lpbot;"
```

## 6. 直接运行验证

```bash
cd "$LPBOT_ROOT"
set -a && source .env.postgres && set +a
./bin/lpbot-shadow --config=configs/config.shadow.toml
```

重点检查：

- 能正常启动，不 panic
- 能连接 `DATABASE_URL`
- 有日志输出 `all components initialized`（或等价启动成功日志）

## 7. systemd 后台运行（推荐）

推荐直接使用仓库模板（已包含 EnvironmentFile=.env.postgres / .env.redis / .env.dashboard / .env.alerting）：

```bash
cd /opt/lpbot/lp-bot-v3
sudo cp deploy/systemd/lpbot-shadow.service /etc/systemd/system/lpbot-shadow.service
sudo systemctl daemon-reload
sudo systemctl enable --now lpbot-shadow
sudo systemctl restart lpbot-shadow
```

模板内容（`deploy/systemd/lpbot-shadow.service`）：

```ini
[Unit]
Description=LP Bot Shadow Mode
After=network.target

[Service]
Type=simple
User=lpbot
WorkingDirectory=/opt/lpbot/lp-bot-v3
# Shadow 必需 env files. 注意：缺省指向 `lpbot-v3` 根目录
# ($LPBOT_ROOT), 若 VPS 路径不同请同步修改此处。
EnvironmentFile=-/opt/lpbot/lp-bot-v3/.env.postgres
EnvironmentFile=-/opt/lpbot/lp-bot-v3/.env.redis
EnvironmentFile=-/opt/lpbot/lp-bot-v3/.env.dashboard
EnvironmentFile=-/opt/lpbot/lp-bot-v3/.env.alerting
ExecStartPre=/opt/lpbot/lp-bot-v3/scripts/validate-shadow-binary.sh /opt/lpbot/lp-bot-v3
ExecStart=/opt/lpbot/lp-bot-v3/bin/lpbot-shadow --config=/opt/lpbot/lp-bot-v3/configs/config.shadow.toml
Restart=always
RestartSec=5
RestartPreventExitStatus=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**关键说明**:
- `EnvironmentFile=-...` 中 `-` 前缀表示该文件可不存在 (missing-tolerable)，不会导致 systemd fail。
- shadow service **不** load `.env.canary` / `.env.live` / `WALLET_PASSPHRASE` / `LPBOT_CONFIRM_LIVE`，canary/live 解锁变量在 shadow service 中物理不可达。
- 部署到不同路径的 VPS 时, 同步修改 6 个 `/opt/lpbot/lp-bot-v3/` 字串。

```bash
cd /opt/lpbot/lp-bot-v3
cp deploy/systemd/lpbot-shadow.service /etc/systemd/system/lpbot-shadow.service
sudo systemctl daemon-reload
sudo systemctl enable --now lpbot-shadow
sudo systemctl restart lpbot-shadow
```

关键说明：
- `ExecStartPre` 使用 `/opt/lpbot/lp-bot-v3/scripts/validate-shadow-binary.sh` 做启动前自检：
  - 校验 `bin/lpbot-shadow --version` 返回 `mode: shadow`
  - 校验 `configs/config.shadow.toml` 的 `[mode].expected = "shadow"`
- 如检查失败，systemd 会停止并持续重试，你会在 `journalctl -u lpbot-shadow` 里看到明确的检查失败日志。

## 7.1 Canary service 预装但不启动

仓库模板：
`deploy/systemd/lpbot-canary.service`

安装到 VPS：

```bash
sudo cp deploy/systemd/lpbot-canary.service /etc/systemd/system/lpbot-canary.service
sudo systemctl daemon-reload
sudo systemctl disable lpbot-canary
sudo systemctl stop lpbot-canary 2>/dev/null || true
```

说明：
- `lpbot-canary` 使用 `bin/lpbot-live` + `configs/config.canary.toml`
- 默认保持 `disabled/inactive`
- readiness 会显示在现有 `9090` dashboard 上，即使服务尚未启动

### 7.2 VPS canary 盈利审计

执行 canary 动作后建议立刻跑一次：

```bash
cd /opt/lpbot/lp-bot-v3
scripts/canary_profitability_evidence.sh
```

可选参数：

- `LPBOT_CANARY_EVIDENCE_WINDOW_HOURS=168`
- `LPBOT_CANARY_EVIDENCE_ROW_LIMIT=50`
- `LPBOT_CANARY_EVIDENCE_POOL_ID=<pool_id>`
- `LPBOT_CANARY_EVIDENCE_OUTPUT=/path/to/xxx.md`

将报告与 `canary_readiness_report.sh`/`canary_cycle.sh` 输出并存储，可形成一次完整动作链路的证据。

## 8. 每次发布更新

```bash
cd "$LPBOT_ROOT"
git fetch origin
git checkout feat/supabase-postgres-deployment
git reset --hard origin/feat/supabase-postgres-deployment
make build-shadow
sudo systemctl restart lpbot-shadow
```

## 9. 回滚

```bash
cd "$LPBOT_ROOT"
git log --oneline -n 10
git checkout <commit-id>
make build-shadow
sudo systemctl restart lpbot-shadow
```

## 10. 运维核对

- `sudo systemctl status lpbot-shadow`
- `sudo journalctl -u lpbot-shadow -n 100 --no-pager`
- `curl http://127.0.0.1:9090/metrics | head -20`
- `redis-cli --scan --pattern 'lpbot:*:heartbeat:*'`
- `ss -lnt | grep 5432`
- 本地/GitHub/VPS 一致性：`make audit-consistency`
- Canary 证据：`scripts/canary_profitability_evidence.sh`

## 11. 全量审计脚本（v3）

固定版审计脚本放在：
`/opt/lpbot/lp-bot-v3/scripts/audit_shadow_vps.sh`

执行示例：

```bash
cd /opt/lpbot/lp-bot-v3
./scripts/audit_shadow_vps.sh 900 60
```

参数说明：

- `900`：审计采样窗口（秒，默认 15 分钟）
- `60`：采样间隔（秒）
- `scripts/overnight-vps-runbook.sh` 每轮会先运行本地一致性审计，再运行 VPS 内部审计。

## 12. 无人值守巡检（8-10 小时）

`scripts/overnight-vps-runbook.sh` 可在后台持续跑 7-10 小时：

```bash
mkdir -p /Users/bendu/.lpbot-ops
LPBOT_HOST=lpbot@157.173.123.24 \
LPBOT_KEY=$HOME/.ssh/lpbot_ed25519 \
LPBOT_CYCLE_MIN=10 \
LPBOT_AUDIT_WINDOW_SEC=20 \
LPBOT_CANARY_EVIDENCE_EVERY_CYCLE=YES \
LPBOT_CANARY_EVIDENCE_WINDOW_HOURS=24 \
LPBOT_CANARY_EVIDENCE_ROW_LIMIT=10 \
LPBOT_AUTOINSTALL_TOOLS=1 \
LPBOT_AUTO_RESTART=0 \
nohup /Users/bendu/lp-bot/v3/scripts/overnight-vps-runbook.sh 8 \
  > /Users/bendu/.lpbot-ops/overnight-8h-$(date +%Y%m%d-%H%M%S).log 2>&1 &
```

说明：
- `LPBOT_AUTOINSTALL_TOOLS=1` 会在审计阶段尝试自动安装 `psql`（`postgresql-client`）与 `redis-cli`（`redis-tools`）；
- 若你只要观测不改系统，请保持 `LPBOT_AUTOINSTALL_TOOLS=0`（默认）；
- 每次有新日志会持续落到 `/Users/bendu/.lpbot-ops/overnight-*.md`。
