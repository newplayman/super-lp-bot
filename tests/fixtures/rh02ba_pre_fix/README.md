# RH-02ba Pre-Fix Fixture Snapshots

本目录包含 RH-02ba 修复**之前**的模块代码快照，仅用于差分测试（Differential Testing，证明旧版会漏、新版能抓）。

## 来源信息
- **来源提交**: `1419621`（"fix(rh-02ba): five more silent failures..."）的父提交（即 `1419621^`）
- **包含文件**:
  - `lp_bsc_fee_velocity_short_backfill_v2_readonly.py`
  - `lp_survival_horizon_ev_model_v1_readonly.py`
  - `lp_survival_out_of_range_risk_v1_readonly.py`
  - `strategy_pivot_d4_realtime_paper_shadow_validation.py`

## 注意事项
- **冻结的历史快照**: 这些文件是不可变的基线快照，**切勿**跟随 `scripts/` 下的现版本更新！
- **背景说明**: 原实现曾使用 `git show <SHA>^:<path>` 动态读取历史 commit。因 2026-09-11 清除历史中的私钥重写了 git 提交历史（所有 SHA 均发生变更），导致硬编码 SHA 失效。为防止 git rebase / filter-branch / cherry-pick 再次破坏测试，将历史版本固化为本目录内的静态快照。
