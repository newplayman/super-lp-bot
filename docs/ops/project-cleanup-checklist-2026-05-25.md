# 项目整理清单（2026-05-25）

## 目标

1. 不把已完成工作误删或从主线误剔除。
2. 把运行态噪音（日志、临时快照、审计产物）与源码隔离。
3. 为后续整理、提交、同步 VPS 提供一版可复用检查清单。

## 已完成但要保留的模块（本地已存在）

1. Solana Tier-C 与 Meteora LP 的探索链路（`cmd/lpbot/solana_*`，以及 `tools/meteora-dlmm-helper`）。
2. Layer-1 观测与监控相关页面和路由（`cmd/lpbot/dashboard.go`、`cmd/lpbot/dashboard.html`）。
3. Tier-C 相关文档与任务清单（`docs/ops/`、`docs/superpowers/`）。
4. 新增的持仓/配置与数据来源调整（`internal/*` 与 `configs/*` 下的相关改动）。
5. Solana LP 相关新增实验文件和回归相关文件（`*_solana_*`、`internal/core/tierc/*`、`internal/adapters/holderconcentration/*`）。

## 本轮先做的边界动作（已完成）

1. 已更新 `.gitignore` 忽略 `tools/**/node_modules/`、`run/`、`run/audits/`、`tmp_sync_placeholder/`、`._*`、`*.log`、`logs/`。
2. 已建立本清单文档，用于下一步逐项核对。

## 执行时别动的清单（冻结）

1. 已有功能实现文件（包括但不限于策略、风控、撮合辅助、可观测性、Solana 试验链路）保持原样。
2. `docs/superpowers` 与 `docs/ops` 里的方案文档先归档再说，不要直接删。
3. 与 VPS 同步脚本与审计脚本先保留，单独评审后再决定是否归类到运行目录。

## 下一步建议顺序

1. 先在 Git 中只做 `status` 清点，不做 `checkout/reset`。
2. 逐一确认 untracked 的 `cmd/lpbot/*`、`internal/core/tierc/*`、`internal/adapters/pool/pancakeswap_v3_solana/*`、`docs/*` 是否要纳入本次主线提交。
3. 把确认保留项分两组提交：`docs` 与 `可运行代码`，再单独处理配置/脚本。
4. VPS 侧对齐时，优先同步 `.gitignore` 与清单文件，避免再次上传二进制日志和临时目录。

