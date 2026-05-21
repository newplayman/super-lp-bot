# VPS Shadow Deployment Runbook

> 基于 `feat/supabase-postgres-deployment` 分支的 Shadow 部署 runbook

目标：统一本地与 VPS 的仓库来源、分支与配置入口，避免因为目录名差异/手工 `.env` 覆盖造成数据库混淆。

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
- `.env` 类文件不入库，只作为启动环境注入。

初始化实例文件：

```bash
cd "$LPBOT_ROOT"
cp .env.example .env
cp .env.postgres.example .env.postgres
chmod 600 .env .env.postgres
```

按实际值编辑：

```bash
vim .env
vim .env.postgres
```

推荐变量：

- `BASE_RPC_PRIMARY`, `BASE_RPC_FALLBACK`, `BASE_WS`, `SOL_RPC_PRIMARY`
- `DATABASE_URL`（VPS 连接 `vps` 上 PostgreSQL 的连接串）
- `REDIS_URL`（建议启用，当前用于 Redis 心跳与运行态探活）

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

保存为 `/etc/systemd/system/lpbot-shadow.service`：

```ini
[Unit]
Description=LPBot Shadow
After=network.target postgresql.service

[Service]
Type=simple
User=lpbot
WorkingDirectory=/opt/lpbot/lp-bot-v3
EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.postgres
EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.redis
ExecStart=/opt/lpbot/lp-bot-v3/bin/lpbot-shadow --config=/opt/lpbot/lp-bot-v3/configs/config.shadow.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lpbot-shadow
sudo systemctl restart lpbot-shadow
```

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

## 12. 无人值守巡检（8-10 小时）

`scripts/overnight-vps-runbook.sh` 可在后台持续跑 7-10 小时：

```bash
mkdir -p /Users/bendu/.lpbot-ops
LPBOT_HOST=lpbot@157.173.123.24 \
LPBOT_KEY=$HOME/.ssh/lpbot_ed25519 \
LPBOT_CYCLE_MIN=10 \
LPBOT_AUDIT_WINDOW_SEC=20 \
LPBOT_AUTOINSTALL_TOOLS=1 \
LPBOT_AUTO_RESTART=0 \
nohup /Users/bendu/lp-bot/v3/scripts/overnight-vps-runbook.sh 8 \
  > /Users/bendu/.lpbot-ops/overnight-8h-$(date +%Y%m%d-%H%M%S).log 2>&1 &
```

说明：
- `LPBOT_AUTOINSTALL_TOOLS=1` 会在审计阶段尝试自动安装 `psql`（`postgresql-client`）与 `redis-cli`（`redis-tools`）；
- 若你只要观测不改系统，请保持 `LPBOT_AUTOINSTALL_TOOLS=0`（默认）；
- 每次有新日志会持续落到 `/Users/bendu/.lpbot-ops/overnight-*.md`。
