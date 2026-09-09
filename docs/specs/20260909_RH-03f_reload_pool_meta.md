# RH-03f：daemon 只在启动时读 pool_meta，于是刷新过的 gas 永远不生效

## 现状（实测 2026-09-09 12:3x UTC）

```
crontab                     无 gas 相关任务
ps                          无常驻 gas 刷新进程
pool_meta.gas_provenance    computed_at = 2026-09-09T08:49:23Z（4 小时前）
lp_rh_shadow_daemon:275     pool_meta_text = Path(args.pool_meta_json).read_text(...)
                            ← 整个进程生命周期内只读这一次
```

主脑今天手动把 `gas_usd_estimate` 从被证伪的 `0.02` 刷成实测 `0.4005`，
但**没有任何机制会再刷新它**，且**即使刷新了 daemon 也读不到**。
这是两层问题，本包只修第二层（让刷新能生效）。

**为什么要紧**：实测最小可行仓位对 gas 近似线性
（`CAPITAL_POLICY_RECOMPUTE_20260909.md`），gas 一天内变了 13%。
一个跑数周的 daemon 拿着启动那一刻的 gas 做全部经济计算，
结论会随时间越来越偏，**而且不会有任何报错**。

## 设计：每个 episode 开始时重读，episode 内保持一致

episode 是分析单元，**中途换输入会让同一 episode 内的步骤不可比**。
所以不是「周期性重读」，而是**在每个 episode 起点重读一次**。
`rh_shadow_episodes.pool_meta_hash` 已存在，重读后自然记录新 hash，
**同一 episode 的所有步骤共用一个 hash，可追溯**。

## 改一个文件

`scripts/lp_rh_shadow_daemon_v1_readonly.py`：

- 把启动时的一次性读取改为一个函数，例如
  `load_pool_meta(path) -> tuple[dict, str]`（返回解析后的 dict 与其 hash），
  **复用现有的 `pool_meta_hash_of`，不要重写**。
- 每个 episode 开始前调用它，用返回值构造该 episode 的配置。
- **★读取或解析失败时，必须沿用上一次成功的值并继续，不得中断循环、
  不得使用空 dict、不得静默换成默认值★**——
  失败要能被看见：把失败计入返回/日志的一个显式字段
  （例如 `pool_meta_reload_errors`），**不要只是 `except: pass`**。
- 首次加载失败（无上一次的值可用）时，维持现有的启动失败行为，不要改。

## 不许动
不改 `pool_meta_hash_of` 的算法（episode 的 hash 语义不能变）。
不改 `lp_rh_shadow_runner_v1_readonly.py`、不改任何闸门、不改 `gas_refresh`。
不联网。单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_pool_meta_reload_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
**不许联网**，用 `tmp_path` 下的临时 JSON 与假时钟／假 episode 驱动。必测：

- **★两个 episode 之间修改文件里的 `gas_usd_estimate`，
  第二个 episode 读到的是**新值**★**（本包的目的）
- **★两个 episode 的 `pool_meta_hash` 因此**不同**★**
- 文件未变时，两个 episode 的 hash **相同**（不产生虚假变更）。
- **★文件在两个 episode 之间被删除 → 沿用上一次的值，循环不中断，
  且错误被显式记录（断言那个字段非空）★**
- **★文件变成非法 JSON → 同上：沿用旧值、不中断、错误可见★**
- **★失败时绝不使用空 dict★**：断言沿用的值里 `gas_usd_estimate` 仍是旧值，
  不是 `None`、不是 0。
- 连续两次失败后再恢复正常 → 第三个 episode 读到新值（可恢复）。
- 同一个 episode 内部，即使文件中途被改，该 episode 用的仍是起点那份
  （断言该 episode 所有步骤的 hash 一致）。
- `load_pool_meta` 返回的 hash 等于 `pool_meta_hash_of(原文文本)`（口径一致）。
- 首次加载失败仍按既有行为处理（不吞掉启动错误）。
- 回归：正常路径下 episode 的其余字段（pool、position_usd、capital_usd 等）不受影响（三条）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_pool_meta_reload_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。

## 落地后（写进 commit message）
本包让刷新**能**生效；**谁来刷新是另一件事**（第一层问题），
需配 cron 定期跑 `lp_rh_gas_refresh --apply`。两者缺一，gas 仍会过期。
