# RH-02av：退出深度的方向靠默认值猜，且拼错的键会被静默吞掉

## 铁证（主脑已核实）

`scripts/lp_rh_exit_depth_v1_readonly.py:276` 附近：

```python
zero_for_one = bool(pool_state.get("zero_for_one", True))
```

而该函数的签名是：

```python
def exit_depth_for_size(*, position_value_usd, max_impact_bps, **pool_state)
```

**两个缺陷叠在一起**：

1. **方向靠默认值**：调用方不传 `zero_for_one` 时默认 `True`（token0→token1）。
   审计实测：同一池状态、$100 仓位、100 bps 上限下，
   默认方向得 `max_exit_usd=20.202, sufficient=False`，
   正确的反方向得 `$100, sufficient=True`——**低估约 4.95 倍**，
   而且把一个本可放行的仓位判成不可退出。
2. **`**pool_state` 吞掉拼错的键**：调用方写成 `zeroForOne` 或 `zero_for_1`
   不会报错，会被静默收进 `pool_state` 然后走默认值。
   **「拼错」与「真的没传」完全不可区分**——这是本项目已确认的第 7 种缺陷模式。

## ★主脑追加的关键约束（19:5x 查到，改变了本包范围）★

**生产调用方是 `scripts/lp_rh_shadow_runner_v1_readonly.py:288`**，它把整个
`pool_meta` 展开传入，而 **`pool_meta.json` 里根本没有 `zero_for_one` 键**
（实测确认）。也就是说 shadow 的 `position_and_exit_depth_pass` 这个 conjunct
**一直在用猜出来的方向做判定**。

因此**本包不得让缺失方向变成失败**——那会让 shadow 的 gate 全部返回
`INPUTS_UNAVAILABLE`，eligible 步直接归零，等于用一个修复打断整条研究线。

**本包只做「让问题可见」，不改变生产行为**：

## 你要做的

1. **保留默认方向，但把它标记出来**：在返回的 dict 里新增一个键
   `direction_source`，取值 `"explicit"`（调用方显式传了 `zero_for_one`）
   或 `"defaulted"`（没传，用了默认 True）。
   **正常路径的其它返回值一个都不许变**——这条是硬要求，
   因为 shadow 每 15 分钟依赖它。
2. **拼错的键要能被发现**：在 `**pool_state` 里检测「看起来像 `zero_for_one`
   但拼错了」的键——至少覆盖大小写与驼峰变体
   （`zeroForOne`、`ZERO_FOR_ONE`、`zero_for_1`、`zeroforone`）。
   命中时返回 `INPUTS_UNAVAILABLE` 并在 reason 里**点名那个拼错的键**，
   而不是当作没传。
3. **先查清有哪些调用方**：`grep -rn 'exit_depth_for_size' scripts/ tests/ | head -20`。
   若有生产调用方现在没传 `zero_for_one`，**不要擅自替它决定方向**——
   在最终报告里列出这些调用点（文件:行号），由主脑决定怎么补。
   **本包只改被调用方，不改调用方。**

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`（另有线在改）、
`scripts/lp_rh_gas_reserve_v1_readonly.py`、`scripts/lp_rh_pnl_v1_readonly.py`、
`scripts/lp_rh_readiness_v1_readonly.py`（这三个另有线在改）、
`scripts/lp_rh_coverage_audit_v1_readonly.py`、任何 `.db`、`pool_meta.json`。
`tests/test_lp_rh_exit_depth_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. 不传 `zero_for_one` → 返回值除新增的 `direction_source="defaulted"` 外
   **与修改前逐键完全一致**（用 `git show HEAD:scripts/lp_rh_exit_depth_v1_readonly.py`
   加载旧版逐键比对，把比对结果贴进报告）。
   **不要**改成 `INPUTS_UNAVAILABLE`——见上面的关键约束。
2. 传 `zeroForOne=True`（驼峰拼错）→ 同样 `INPUTS_UNAVAILABLE`，reason 点名该键。
3. **防回归**：显式传 `zero_for_one=True` 与 `zero_for_one=False`，
   返回值与**修改前完全一致**。用 `git show HEAD:scripts/lp_rh_exit_depth_v1_readonly.py`
   拿到旧版做对照，**把两组实际数值贴进报告**。
4. 用真实 `reports/lp_rh/pool_meta.json` 的池状态，
   分别用两个方向跑 $100 / 100bps，把两个 `max_exit_usd` 贴进报告
   （审计说是 20.202 与 100，验证一下是否复现）。
5. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_exit_depth_v1_readonly.py -q -p no:cacheprovider`
   全绿；若有既有测试因不再有默认方向而失败，
   **允许在那些测试的调用处补上显式 `zero_for_one=`**，
   但不许删测试、不许恢复默认值，并在报告里逐条说明改了哪几行。
6. 显式传 `zero_for_one=True` → `direction_source == "explicit"`，
   其余返回值与不传时**完全一致**（因为默认值就是 True，这验证了
   「标记」没有改变任何计算）。
7. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3` 贴出尾部。
   基线是 **5 failed / 4494 passed**，5 个红全是
   `test_lp_rh_first_step_accrual`（已知，另一条线在修），**不得新增 failed**。

## 纪律（违反即退回）

- **不要执行任何 git 写命令**（`git show` 只读可用）。
- 单次 Write/Edit ≤ 150 行或 6000 字符。
- 不要整读 >300 行的文件，用 `sed -n 'a,bp'`。
- 不要重启 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 命令输出只贴尾部。
