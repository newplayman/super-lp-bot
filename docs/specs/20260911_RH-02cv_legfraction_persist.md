GOAL:
把 `leg_fraction` 与 `leg_fraction_status` 接进落库路径。它们现在被算出来了,但**永远到不了数据库**。

## 现象(已实测,直接用)

`scripts/lp_rh_netcover_inputs_v1_readonly.py` 的 `assemble_rh_clmm_inputs` 会返回这两个字段。
在生产数据上实测确实算出来了:

```
leg_fraction        = 0.4756
leg_fraction_status = COMPUTED
```

但落库的记录里它们是 **None**:

```sql
-- rh_economic_evaluations.cost_components_json 最新一条的全部键:
entry_cost_usd, exit_cost_usd, exit_gas_reserve_usd, exit_latency_loss_usd,
gas_usd, gas_usd_source, il_ev_usd, lvr_ev_usd, reward_conversion_cost_usd, slippage_usd
-- 没有 leg_fraction,也没有 leg_fraction_status
```

## 真因(已定位)

```
scripts/lp_rh_shadow_runner_v1_readonly.py:1149-1155
    "cost_components_json": json.dumps(
        dict(
            {k: gated.get(k) for k in _COST_COMPONENT_KEYS},   ← 固定白名单
            gas_usd_source=...,
            exit_gas_reserve_usd=...,
            size_interval=size_interval_meta,
        ), sort_keys=True),
```

`_COST_COMPONENT_KEYS`(约 1030 行前后定义)只有八个成本数值键,
新加的两个字段不在里面,于是被静默丢弃。

**为什么这很重要**:没有这两个字段,事后看一条记录**分不出**它用的是
真算出来的比例(0.4756)还是 fail-close 回退的 1.0。
commit `c19aef0` 的设计是「回退与标记必须同时发生」——标记落不了库,这条就只做了一半。

## 要做的事

只改 `scripts/lp_rh_shadow_runner_v1_readonly.py` 与
`tests/test_lp_rh_shadow_runner_v1_readonly.py`。

1. 让 `leg_fraction` 与 `leg_fraction_status` 进入 `cost_components_json`。
   - **不要**简单地把它们塞进 `_COST_COMPONENT_KEYS` —— 那个元组是「成本数值」的集合,
     被别处用来求和/遍历的话会被污染。**先 grep 确认 `_COST_COMPONENT_KEYS` 还被谁用了**,
     在报告里写明你查到的全部引用点和你的判断依据。
   - 若它只在这一处使用,可以酌情扩充;若还有别处使用,就按 `gas_usd_source` 的写法
     单独作为关键字参数传进 `dict(...)`。**照既有惯例,不要发明新结构。**
2. `leg_fraction` 用 `_economic_str` 存成定点小数字符串(与 `00240e9` 的精度约定一致),
   **不要用 float**。`leg_fraction_status` 是字符串原样存。
3. 取不到时存 `None`,**不要存 0、不要存空字符串、不要省略这个键**。

## 不许动

- 不要改 `scripts/lp_rh_netcover_inputs_v1_readonly.py`(它已经算对了,只是没被取走)。
- 不要改换腿比例的计算逻辑、不要改任何成本数值。
- 不要改 `size_interval` 那一块。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要碰 `scripts/lp_rh_coverage_report_v1_readonly.py`(另一个任务在建它)。
- 不要写 `reports/lp_rh/` 下的任何数据库;测试用 `tmp_path`,用仓库自己的 `migrate()` 建 schema。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试(≥4 条新增)

本项目已九次出现「测试构造的输入进不去被测代码」。**写完把被测代码临时改坏,
确认测试真的变红,再改回来。**

1. 跑一个 episode → `rh_economic_evaluations.cost_components_json` 里
   **确实带** `leg_fraction` 与 `leg_fraction_status` 两个键
2. 比例算得出时 → `leg_fraction_status == "COMPUTED"`,`Decimal(leg_fraction)` 等于被测模块返回的值
3. 比例算不出(造一个缺 `range_pct` 的 pool_meta)→ 落库的 `leg_fraction` 是 **1.0**、
   `leg_fraction_status` 以 `FALLBACK_FULL_POSITION:` 开头(**证明回退在库里看得见**)
4. 回归保护:八个既有成本键的数值**一个都没变**
5. 断言用 `Decimal(...)` 比较,**不要把今天算出来的那串数字钉进断言**
   ——本项目已四次因「把当前数据状态写进断言」出问题

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`(12 万文件)。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q`(全绿)
2. `grep -n "leg_fraction" scripts/lp_rh_shadow_runner_v1_readonly.py`(应出现在落库那一段)
3. 报告里写明:`_COST_COMPONENT_KEYS` 的全部引用点,以及你选择哪种接法、为什么
4. **不要跑全量测试**(另有 worker 在并行跑,会撞车)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
