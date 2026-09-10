# AUDIT：扫描器规则1（宽容默认值）在热路径上到底有几条（2026-09-10）

- 性质：**只读**。主脑亲自完成（两次派活失败后收回，原因见文末）。
- 输入：`python3 scripts/lp_silent_failure_lint_v1_readonly.py --json`（实时扫描，
  **不是** `reports/silent_failure_lint_baseline.json`——基线已随今晚的代码改动漂移）。
- 快照：HEAD = `8e54926`，实时扫描 rule1 共 **249** 条。

## 结论

热路径上只有 **1 条**真缺陷，其余全是 Python 计数惯用法。

三个热路径入口文件**自身**共 6 条 rule1 命中：

| 文件:行 | 代码 | 判定 |
|---|---|---|
| `lp_rh_shadow_runner_v1_readonly.py:483` | `pool_meta.get("max_impact_bps", 50)` | **A — 真缺陷** |
| `lp_rh_readiness_v1_readonly.py:715` | `by_day.get(t.date(), 0) + 1` | D — 计数惯用法 |
| `lp_rh_shadow_runner_v1_readonly.py:809` | `counts.get(name, 0) + 1` | D — 计数惯用法 |
| `lp_rh_shadow_runner_v1_readonly.py:818` | `status_counts.get(s.primary_status, 0) + 1` | D — 计数惯用法 |
| `lp_rh_shadow_runner_v1_readonly.py:820` | `blocker_counts.get(s.dominant_blocker, 0) + 1` | D — 计数惯用法 |
| `lp_rh_shadow_runner_v1_readonly.py:862` | `steps_without_nav_reasons.get(r, 0) + 1` | D — 计数惯用法 |

`counter.get(k, 0) + 1` 里的 `0` 是**唯一正确语义**（还没数到过就是零次），
不是宽容默认值。这五条是扫描器的结构性误报。

### 唯一那条真缺陷

```python
# scripts/lp_rh_shadow_runner_v1_readonly.py:483
max_impact_bps=Decimal(str(pool_meta.get("max_impact_bps", 50))),
```

它在 `position_and_exit_depth_pass` 这一项终闸的判定路径上。
配置里缺了 `max_impact_bps`，退出深度闸门就**静默改用 50 bps 的宽容阈值**，
而不是 fail-close 阻断。

**当前不会触发**——生产的 `reports/lp_rh/pool_meta.json` 里有这个键。
但这正是「静默假绿」的典型形态：一次配置遗漏就能把一道风控闸门变成橡皮图章，
且不报错、不留痕。

**待修**（`lp_rh_shadow_runner_v1_readonly.py` 当前正被 RH-02bq 改动，需排队）：
缺 `max_impact_bps` 时应当 `fail("position_and_exit_depth_pass", ...)`，
与同一函数里 `pool_meta lacks tick_data` 的处理保持一致。

## 规则1 的信噪比（249 条全体）

原以为计数惯用法是噪音大头，**实测推翻**：

| 模式 | 条数 | 占比 |
|---|---:|---:|
| 其它（真正的宽容默认值） | 219 | 88.0% |
| 计数自增 `.get(k, 0) + N` | 24 | 9.6% |
| 空容器默认 `.get(k, [])` / `.get(k, {})` | 6 | 2.4% |

「其它」里的典型：

```python
int(state.get("pool_count", 0) or 0)                  # 旧线脚本
cp.get("usdc_balance_raw", 0) < 10 * 10**6            # 余额缺失当成 0
report.get('position_coverage', {}).get('unique_position_identities', 0)
```

所以规则1 本身是有效的，只是**绝大多数命中落在 RH 转向之前的废弃旧线脚本里**
（BSC 费率速度、Meteora DLMM、Polymarket 竞品、tier_b/tier_c 回放、
portfolio paper runner 等），不参与当前 shadow 与毕业判定。

判定这 243 条非入口文件命中的可达性需要真正的调用图分析，
**价值低于成本，暂不做**。热路径部分已由本报告穷尽。

## 两次派活为什么失败（记下来，别再兜这个圈子）

RH-02bl 与 RH-02bl-2 先后派给 gemini，两次都退回，**失败方式完全相同**：

```
第一轮：hits=248，与基线差集 66/65
第二轮：hits=248，与实时扫描差集 79/77，summary 与第一轮一字不差
```

第二轮的 spec 已经明确要求「先跑扫描器出 JSON，再写脚本加字段，
file/line/fingerprint 原样复制」，仍然产出了同一份东西。
核实时发现行号指向的是**旧代码**：

```
分级表说   runner:745 是 get("name", 0)
实际 745 行 decision.dominant_blocker, nav, step_net_pnl, hodl_value,
```

**它的分级判断本身是对的**——分布（A:1 B:7 C:216 D:24）与主脑独立核实的
热路径结论一致，那条 A 级也判对了。砸的只是「把条目精确搬运过来」这一半。

**教训：需要逐字精确搬运的工作不要交给模型。** 机械部分（读扫描器输出、
生成带正确身份的骨架）主脑写十行脚本就能做对；模型只该负责填判断字段。
本报告的热路径部分主脑用三条命令做完，成本远低于两轮派活。
