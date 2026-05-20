# VPS Shadow Deployment Runbook

> Shadow mode部署 - 不进行真实交易，仅模拟执行

## 架构

```
本地开发机 (git push)
       ↓
    GitHub/Gitea
       ↓
VPS (git pull + make build + systemctl restart)
```

## 前置条件

### VPS
1. 安装 Go 1.21+
2. 安装 PostgreSQL
3. Git 已配置 (可选: 部署密钥)
4. Firewall 开放端口: 9090 (metrics)

### 本地
1. 代码已推送: `git push origin main`
2. 已打 tag: `git tag v0.3.0-shadow-ready && git push --tags`

## 部署步骤

### 1. 本地开发完成，推送代码

```bash
cd ~/lp-bot/v3
git add -A
git commit -m "chore: v0.3.0-shadow-ready"
git tag v0.3.0-shadow-ready
git push && git push --tags
```

### 2. VPS 登录，拉取代码

```bash
ssh user@vps
cd ~/lp-bot/v3

# 如果是首次部署
git clone https://github.com/YOUR_USER/lpbot.git
cd lpbot
git checkout v0.3.0-shadow-ready

# 已有仓库则拉取更新
git pull origin v0.3.0-shadow-ready
```

### 3. VPS 安装依赖

```bash
go mod download
make tidy
```

### 4. 创建配置文件

```bash
mkdir -p ~/lp-bot/v3/data
```

创建 `~/lp-bot/v3/configs/config.shadow.toml`:

```toml
[platform]
log_level = "info"

[platform.prometheus]
enabled = true
port = 9090

[platform.telegram]
token = "YOUR_BOT_TOKEN"           # 可选
chat_id = 123456789                # 可选

[store]
type = "postgres"
host = "localhost"
port = 5432
user = "lpbot"
password = "YOUR_PASSWORD"
database = "lpbot_shadow"
sslmode = "require"

[chains.base]
rpc_primary = "https://mainnet.base.org"
rpc_fallback = ["https://base.publicnode.com"]

[chains.solana]
rpc_primary = "https://api.mainnet-beta.solana.com"

[chains.base.keystore]
type = "file"
path = "/home/user/lp-bot/v3/keystore/UTC--xxx"
password_env = "KEYSTORE_PASSWORD"

[execution]
dryrun = false   # shadow模式为false
mev_protection = true
```

### 5. VPS 构建

```bash
cd ~/lp-bot/v3
make build-shadow
```

### 6. 初始化数据库 (首次)

```bash
sudo -u postgres psql -c "CREATE DATABASE lpbot_shadow;"
```

### 7. 设置环境变量

```bash
export KEYSTORE_PASSWORD="your_keystore_password"
export DATABASE_URL="postgres://lpbot:YOUR_PASSWORD@localhost/lpbot_shadow?sslmode=require"
```

### 8. 测试运行

```bash
cd ~/lp-bot/v3
./bin/lpbot-shadow --config=./configs/config.shadow.toml
```

观察日志，确认：
- 无 panic
- Metrics 端点启动: `curl http://localhost:9090/metrics`
- 程序正常运行

### 9. 配置 systemd (后台运行)

创建 `/etc/systemd/system/lpbot-shadow.service`:

```ini
[Unit]
Description=Liquidity Bot Shadow Mode
After=network.target postgresql.service

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/lp-bot/v3
Environment="KEYSTORE_PASSWORD=your_keystore_password"
Environment="DATABASE_URL=postgres://lpbot:YOUR_PASSWORD@localhost/lpbot_shadow?sslmode=require"
ExecStart=/home/user/lp-bot/v3/bin/lpbot-shadow --config=/home/user/lp-bot/v3/configs/config.shadow.toml
Restart=always
RestartSec=5
RestartPreventExitStatus=0

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lpbot-shadow
sudo systemctl start lpbot-shadow
```

## 验证部署

```bash
# 检查状态
sudo systemctl status lpbot-shadow

# 查看日志
sudo journalctl -u lpbot-shadow -f

# 检查 metrics
curl http://localhost:9090/metrics | head -20
```

## 后续更新

代码更新后，在 VPS 上:

```bash
cd ~/lp-bot/v3
git pull origin main
make build-shadow
sudo systemctl restart lpbot-shadow
sudo journalctl -u lpbot-shadow -n 50 --no-pager
```

## 回滚

```bash
# 查看历史 tag
git tag -l | tail -5

# 回滚到上一个版本
git checkout v0.2.x
make build-shadow
sudo systemctl restart lpbot-shadow
```

## 目录结构

```
~/lp-bot/v3/
├── bin/
│   └── lpbot-shadow          # 构建产物
├── configs/
│   └── config.shadow.toml    # 配置文件
├── data/                     # SQLite/数据目录
├── docs/
├── internal/
└── Makefile
```

## 故障排查

| 问题 | 解决 |
|------|------|
| 启动 panic: keystore not found | 检查 `chains.base.keystore.path` 配置 |
| 数据库连接失败 | 检查 PostgreSQL 运行状态 |
| Metrics 端点无响应 | 检查防火墙 9090 端口 |
| 服务启动失败 | `journalctl -u lpbot-shadow -n 100` 查看日志 |

## 下一步

确认 shadow 运行稳定后，可升级到 live mode:
1. 测试 Bootstrap 对账功能
2. `git checkout v0.4.0-live-ready` (新 tag)
3. `make build-live`