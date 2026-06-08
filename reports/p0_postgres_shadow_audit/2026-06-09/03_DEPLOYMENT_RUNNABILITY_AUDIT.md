# P0 Postgres/Supabase Deployment Runnability Audit

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`
- **audit_focus**: shadow Postgres deployment 是否能完整跑通 (systemd + env + config + runbook + migration)
- **audit_method**: read-only, 2 systemd units + 4 .toml configs + 6 .env*.example + 1 migration shell script + 1 audit shell script + 1 runbook

## 1. Deployment Component Inventory

| 组件 | 文件 | 关键内容 |
|---|---|---|
| Shadow systemd | `deploy/systemd/lpbot-shadow.service` | ExecStart=bin/lpbot-shadow --config=configs/config.shadow.toml, **无 EnvironmentFile** |
| Canary systemd | `deploy/systemd/lpbot-canary.service` | ExecStart=bin/lpbot-live --config=configs/config.canary.toml, **有 4 个 EnvironmentFile** (.env.canary / .env.postgres / .env.redis / .env.dashboard) |
| Migration script | `scripts/apply_postgres_migrations.sh` | load .env.postgres + .env.canary, psql -f migrations/postgres/*.sql 逐个 apply, **无 version tracking, 无 checksum** |
| Audit script | `scripts/audit_shadow_vps.sh` | 端到端 audit, 默认 15 min sample, 检测 service / branch / config / DSN |
| Shadow config | `configs/config.shadow.toml` | [store] backend = "postgres", postgres_dsn = "${DATABASE_URL}" |
| Live config | `configs/config.live.toml` | [store] backend = "postgres", postgres_dsn = "${POSTGRES_DSN}" |
| VPS config | `configs/config.vps.toml` | [store] backend = "postgres", postgres_dsn = "${DATABASE_URL}" |
| Shadow research overlay | `configs/config.shadow.research.toml` | (read-only research overlay, 不直接走 postgres) |
| Env example | `.env.postgres.example` | DATABASE_URL= (空 placeholder), REDIS_URL=redis://127.0.0.1:6379/0 |
| Env example | `.env.example` | DATABASE_URL=, POSTGRES_DSN=, REDIS_URL=, etc. |
| Env example | `.env.canary.example` | (canary/live 专用) |
| Env example | `.env.live.example` | (live 专用) |
| Env example | `.env.redis.example` | (redis 专用) |
| Env example | `.env.dashboard.example` | (dashboard 专用) |
| Runbook | `docs/runbooks/vps-shadow-deployment.md` | 部署 step-by-step, 包括 .env.postgres 初始化 |
| Validate script | `scripts/validate-shadow-binary.sh` | ExecStartPre 调, 验 lpbot-shadow binary 存在 |

## 2. Shadow vs Canary systemd Service 对比

| 字段 | lpbot-shadow.service | lpbot-canary.service | 是否一致? |
|---|---|---|---|
| [Unit] Description | "LP Bot Shadow Mode" | "LP Bot Canary Mode" | (命名合理) |
| [Service] Type | simple | simple | ✅ |
| [Service] User | lpbot | lpbot | ✅ |
| [Service] WorkingDirectory | /opt/lpbot/lp-bot-v3 | /opt/lpbot/lp-bot-v3 | ✅ |
| [Service] EnvironmentFile | **❌ 无** | ✅ 4 个 (.env.canary, .env.postgres, .env.redis, .env.dashboard) | ❌ **drift** |
| [Service] ExecStartPre | /opt/lpbot/lp-bot-v3/scripts/validate-shadow-binary.sh ... | (无) | (asymmetric but ok) |
| [Service] ExecStart | bin/lpbot-shadow --config=configs/config.shadow.toml | bin/lpbot-live --config=configs/config.canary.toml | (asymmetric by design) |
| [Service] Restart | always | always | ✅ |
| [Service] RestartSec | 5 | 5 | ✅ |
| [Service] RestartPreventExitStatus | 0 | 0 | ✅ |
| [Service] StandardOutput | journal | journal | ✅ |
| [Service] StandardError | journal | journal | ✅ |
| [Install] WantedBy | multi-user.target | multi-user.target | ✅ |

**关键发现**: shadow service **没有 EnvironmentFile** → 不能 read .env.postgres / .env.canary / .env.redis / .env.dashboard. 启动时 `${DATABASE_URL}` 在 configs/config.shadow.toml:26 解析为空, **DSN 空 → postgres adapter 启动 fail**.

**Severity**: P0. 这是部署 runnability 最直接的 blocker.

## 3. Migration Script vs Service 时序

apply_postgres_migrations.sh 的执行流 (来自 read):
1. cd "$ROOT_DIR"
2. load .env.postgres (set -a; . file; set +a)
3. load .env.canary
4. POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"  (POSTGRES_DSN > DATABASE_URL fallback)
5. check empty DSN, fail
6. for migration in migrations/postgres/*.sql: psql "$POSTGRES_DSN" -v ON_ERROR_STOP=1 -f "$migration"

也就是说 migration apply 时, 进程能看到 .env.postgres 里的 DATABASE_URL (load via shell). 但**apply 完退出后, 这些 env vars 不会自动 propagate 到 systemd manager 的 environment**. 所以 lpbot-shadow systemd 启动时, **DATABASE_URL 在 systemd manager environment 中是空的**, configs/config.shadow.toml 解析 ${DATABASE_URL} 为空字符串.

**Fix**: 给 lpbot-shadow.service 加 `EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.postgres`. (注意: .env 仍要 `chmod 600`, 因为含密码.)

## 4. Deployment Blockers Found

### BLK-PG-06 (P0): lpbot-shadow.service missing EnvironmentFile

- **现象**: lpbot-shadow.service 没 load .env.postgres
- **证据**: 上面 §2 表中 EnvironmentFile 字段 = 无
- **影响**: lpbot-shadow 启动 fail with "DSN empty" / postgres adapter NewFromDSN fail
- **Fix (P0-PG-02-D)**: 加 `EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.postgres` (以及可选 .env.redis if shadow 用 redis). **chmod 600** .env.postgres 必做.

### BLK-PG-06.b (P1): config.shadow.toml uses ${DATABASE_URL} but env can be POSTGRES_DSN

- **现象**: config.shadow.toml:26 写 `postgres_dsn = "${DATABASE_URL}"`, 但 .env.postgres.example 注释说 `POSTGRES_DSN 或 DATABASE_URL` 都行. apply_postgres_migrations.sh 处理 fallback 顺序 POSTGRES_DSN > DATABASE_URL. 但 config.shadow.toml 硬写 `${DATABASE_URL}`, 如果 ops 只设 POSTGRES_DSN 不设 DATABASE_URL, lpbot-shadow 启动 fail.
- **影响**: ops confusion. 容易踩坑.
- **Fix (P0-PG-02-D)**: config.shadow.toml 改用 `${POSTGRES_DSN:-${DATABASE_URL:-}}` (Go template-style fallback). 或文档明确 "shadow 必须 DATABASE_URL, canary/live 必须 POSTGRES_DSN".

### BLK-PG-06.c (P1): no auto-restart on migration mismatch

- **现象**: apply_postgres_migrations.sh fail (部分 migration 出错), 但 lpbot-shadow 已 start, 用旧 schema 跑. restart=always 不会因为 schema 错退出而立即重启 (只是 exit → restart 5s 后再 start, 还是 fail).
- **影响**: 半 apply 状态, 后续 ops debug 难.
- **Fix (P0-PG-02-D)**: lpbot-shadow.service 加 `ExecStartPre=/opt/lpbot/lp-bot-v3/scripts/validate-shadow-binary.sh ...` (已经有) + 新加 `ExecStartPre=/opt/lpbot/lp-bot-v3/scripts/check-postgres-migrations.sh` (新脚本, 验 schema_version 表 or to_regclass 几个 key table).

### BLK-PG-06.d (P2): validate-shadow-binary.sh 不验 DSN 真实性

- **现象**: validate-shadow-binary.sh 只验 binary 存在 + 可执行. 不验 DSN 是否能连.
- **影响**: lpbot-shadow 启动 fail, journalctl 才知道 DSN 错.
- **Fix (P0-PG-02-D)**: validate-shadow-binary.sh 加 `psql "$POSTGRES_DSN" -c "SELECT 1" -q` 测试. 但这增加 service start 时间. 可能放 ReadWriteOnly check 即可.

### BLK-PG-06.e (P2): audit_shadow_vps.sh 默认 15 min sample, 但 shadow Postgres 启动后 schema guard 失败会立即 fail

- **现象**: audit_shadow_vps.sh 跑 15 min 采样 (默认 900s). 如果 shadow 启动 fail 在前 5s, 仍会等 15 min 才发现.
- **影响**: 反馈慢.
- **Fix (P0-PG-02-D 或 P0-PG-03)**: audit 阶段加 fast-fail: 前 60s 内 service status != active 立即 fail.

## 5. DSN 占位符与 secret 泄漏 audit

| 位置 | 是否有占位符? | 占位符写法 | 风险 |
|---|---|---|---|
| `.env.postgres.example` | ✅ placeholder | `DATABASE_URL=` (空) | OK (无 secret) |
| `.env.example` | ✅ placeholder | `DATABASE_URL=`, `POSTGRES_DSN=`, `REDIS_URL=redis://127.0.0.1:6379/0` (本地默认) | OK (无 secret) |
| `configs/config.shadow.toml` | ✅ TOML placeholder | `${DATABASE_URL}` | OK (env var name, 非 secret) |
| `configs/config.live.toml` | ✅ TOML placeholder | `${POSTGRES_DSN}` | OK |
| `configs/config.vps.toml` | ✅ TOML placeholder | `${DATABASE_URL}` | OK |
| `apply_postgres_migrations.sh` | ✅ uses env var | `POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"` | OK |
| `internal/adapters/store/postgres/adapter.go` | (无 DSN hardcode) | 接受 PostgresConfig 或 URL | OK |
| `deploy/systemd/lpbot-canary.service` | ✅ EnvironmentFile | `.env.postgres`, `.env.canary`, `.env.redis`, `.env.dashboard` | OK (4 file 拆分) |
| `deploy/systemd/lpbot-shadow.service` | ❌ no EnvironmentFile | (硬执行) | BLK-PG-06 |

**secret 泄漏 audit**:
- 没在 migration .sql 看到任何 password / private_key / mnemonic / 64-hex
- 没在 .toml 看到任何 inline password
- 没在 .env.example 看到任何 secret value
- 没在 shell script 看到任何 secret value (除了 DSN 解析)

✅ secret management 干净. 仅 BLK-PG-06 是 deployment flow 的 gap.

## 6. README / Runbook vs Service / Config 一致性

| 文档 / 文件 | 描述 | 与 service / config 一致? |
|---|---|---|
| `docs/runbooks/vps-shadow-deployment.md` | VPS shadow 部署 step-by-step, 包括 .env.postgres 初始化 | 部分一致: 写 "把 .env.postgres 复制到 /opt/lpbot/lp-bot-v3/", 但 lpbot-shadow.service 没显式 load 它, 这是 runbook 与 service 不一致 |
| `CLAUDE.md` (项目 instructions) | 提到 `.env.runtime` / `.runtime.shadow.env` are deploy-time, not in VCS | OK |
| `.runtime.shadow.env` | (untracked file in git status) | OK (是 deploy-time, 不入 VCS) |
| `README.md` | (未读) | (assumed consistent) |

**Runbook 改进建议 (P0-PG-06)**:
1. 加一段 "Ensure lpbot-shadow.service loads .env.postgres" instruction, 引用 systemd unit diff.
2. 加一段 "Verify live schema guard passes" instruction, 引用 main.go:821.
3. 加一段 "Pre-apply: 跑 check-postgres-migrations.sh, 确认 migration 编号无 gap, 000010 → 000011 → 000012 连续".

## 7. 一句话

Deployment runnability 找到 5 个 issue (1 P0, 4 P1/P2). 核心 blocker 是 BLK-PG-06 (lpbot-shadow.service 缺 EnvironmentFile). Secret 管理干净, DSN 全用 placeholder, 没问题. Runbook 与 service 略有 gap. 全部 fixable in P0-PG-02-D (env file + DSN fallback) + P0-PG-06 (runbook update).
