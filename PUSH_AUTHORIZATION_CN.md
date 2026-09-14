# PUSH_AUTHORIZATION_CN.md

Owner 显式批准本次 feature commit/push 范围；来源与边界对账清楚。

## 1. 「不推送」限制的实际来源（按条款）

| 限制 | 来源 | 是否本次放宽 |
|------|------|------------|
| 不 `rm -rf` / 删已装应用 / 格式化 | CLAUDE.md §安全硬线 1 | 否（本次不动） |
| 不 `git reset --hard` / `systemctl restart` 生产服务 | CLAUDE.md §安全硬线 1 | 否（本次不动） |
| 不动资金 / 真实订单 / 钱包私钥 | CLAUDE.md §安全硬线 1 | 否（本次不动） |
| 不触碰家用路由器 / 局域网管理 | CLAUDE.md §安全硬线 5 | 否（本次不动） |
| **不自动 push，需 owner 批准** | 历史 paper-release 文档惯例；本任务上一轮 owner 没说批准 | **是：本任务 owner 显式批准「feature commit/push + Actions 读取」** |

唯一限制是惯例性「等 owner 决定」——不是冻结硬线。本任务补充指示明文放行：

> "Owner 采用本补充任务后，允许本任务 feature commit/push 和 Actions 读取；
> 不允许 main、force push、部署、生产服务变更或交易。"

## 2. 本次 owner 授权范围（明确）

**允许**：
- `git add scripts/lp_rh_paper_daemon_entry_v1.py tests/test_lp_rh_paper_daemon_entry_v1.py scripts/lp_rh_paper_data_validity_v1.py tests/test_lp_rh_paper_data_validity_v1.py PAPER_MIN_RELEASE_V1_CN.md PAPER_START_REQUEST_CN.md BLOCKERS_20260914_RC_CN.csv ACCEPTANCE_MATRIX_20260914_CN.md PUSH_AUTHORIZATION_CN.md STAGE_A_REALDATA_SNAPSHOT.json`
- `git commit -m "..."`（一次性 commit，本次完整 fix 集）
- `git push origin feat/prd-v2.1-m0-shadow`（HEAD 推到同一 feature 分支；不新建）
- 推送后读 GitHub Actions 日志（网页目视 / `gh run view`）

**禁止**：
- 推送到 `main` / `master`
- `git push --force` / `--force-with-lease` / `-f`
- 任何 workflow 的 `workflow_run` 触发（即使是自添加的）
- 任何部署 step（kubectl apply、aws、gcloud、terraform、render、vercel、fly）
- 改动生产 systemd unit / `systemctl restart` 任何服务
- 任何签名 / 广播 / 真实交易 / 私钥导入 / 资金移动
- 任何 verify_calldata / 白名单 / Live signer / STOCK/MEME/V4 新范围（owner 显式 deny）

## 3. 推送前 workflow 自检（必须逐条确认）

```
[ ] 1. git status --short 仅 4 文件 modified（M）+ 7 文件 untracked（??）
[ ] 2. 没有任何 deployment/manifest/k8s/*.yaml / helm/* / terraform/* 改动
[ ] 3. 没有 .github/workflows/*.yml 改动
[ ] 4. 没有 configs/config.live.toml / config.canary.toml 改动
[ ] 5. 没有 secrets / .env / *.key / *.toml.sha256 改动
[ ] 6. HEAD = 候选 commit SHA（TESTED_CODE_SHA），分支 = feat/prd-v2.1-m0-shadow
[ ] 7. commit message 不含 [skip ci] / [no ci]
[ ] 8. push 命令用 git push origin feat/prd-v2.1-m0-shadow（非 main、非 --force）
```

### 3.1 自动校验脚本

```bash
bash scripts/check_pre_push_safe.sh
```

脚本输出全 `[OK]` 才允许 push；任一 `[FAIL]` 立即停止，先排查再提交。

## 4. 远端 Actions 一致性（Gap 4 重复验证）

- 推送后等 `audit-regression.yml` + `ci.yml` + `shadow-smoke-gate.yml`（若 path 命中）全部完成
- 全部 PASS → ACCEPT
- 任一 FAIL → 立即 NOT_PROVEN，**不引用本地通过数**（per Gap 4 一致性）
- 若只有 `migration-quality-gate` 触发且 FAIL（本次不触发，无 migration 改动），同样 NOT_PROVEN

## 5. 推送后本地收尾

- 不重启 5 个 RH 长跑进程
- 不重启任何 systemd unit
- 不发任何 webhook / Telegram / Slack 通知
- 本次 commit 的 `head_sha` 即 `TESTED_CODE_SHA`，写进 ACCEPTANCE_MATRIX