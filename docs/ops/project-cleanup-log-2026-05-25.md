# 项目整理记录（2026-05-25）

这次整理目标是“降噪，不清仓”。  
原则：**不动业务代码实现**、不删除已完成模块，只把执行产物和环境相关文件与源码清晰分离。

## 本次整理范围

- 新增/更新 `.gitignore`：
  - 屏蔽 `tools/**/node_modules/`
  - 屏蔽 `run/` 与 `run/audits/`
  - 屏蔽 `tmp_sync_placeholder/`、`._*`、`*.log`、`logs/`
- 保留并继续使用的已完成工作清单（仅说明）
  - LP 风险与执行流程骨架仍按现状保留，包括策略、回测与风险控制相关实现。
  - 已完成的 Solana/Meteora 预检与建仓就绪流程文件仍保持在源码中，`cmd/lpbot/solana_meteora_lp_*.go`、`tools/meteora-dlmm-helper`。
  - Tier-C 相关脚本与审计文档（`scripts/`、`docs/superpowers`、`docs/ops`）不改动。

## 后续操作（建议）

1. 逐条确认 `run/` 与 `tmp_sync_placeholder/` 的历史文件先移动到外部归档目录，再按需恢复到可复现工单。
2. 先按“运行脚本目录（可执行）”与“报告目录（只读）”分层存放，再继续补齐文档到 `docs/ops`。
3. 在确认数据库与配置清理完成前，不做大规模文件搬迁，避免把未提交的修复夹带进去。

