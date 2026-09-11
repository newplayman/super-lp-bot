GOAL:
让「经济模型用的池子状态有多旧」在证据里可见。现在它完全不可见,而且实测已经旧了 **30.8 小时**。

## 已确认的事实(实测,直接用)

`rh_market_states` 表的真实列是:
```
asset_address, sample_time, chain_id, source_payload_hash, session, health_flags_json,
reference_bid, reference_ask, reference_mid, reference_age_secs, multiplier_human,
oracle_paused, derived_block_hash, derived_block_number, source_event_time,
fee_growth_global_0, fee_growth_global_1
```
**没有 `sqrt_price_x96`,没有 `liquidity_raw`,没有 `tvl_usd`。**

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `_evidence_for` 只在样本自己没有该键时
才从 `pool_meta` 取(`_POOL_EVIDENCE_KEYS`,约 153 行)。因为样本永远没有这三个键,
**它们永远来自静态文件 `reports/lp_rh/pool_meta.json`**。

该文件 mtime = `2026-09-10 06:39:28 UTC`,**至今 30.8 小时,没有任何代码会写它**
(已 grep 确认:引用它的五个脚本没有一个执行写入)。

后果实测:
- 静态 `sqrt_price_x96` 推出的池价 = 2484.0092,采集器最新 `reference_mid` = 2507.2276,**偏离 +0.93%**
- **一轮 200 步里 `leg_fraction` 恒为 0.4756、`entry_cost_usd` 恒为 0.047980** ——
  它们算的是同一个冻结池态,根本不随行情变化
- `pool_meta.json` 的 `observed_at` 与 `as_of` 两个字段**都是 None**

## 要做的事(只让它可见,**不要去更新 pool_meta**)

只改 `scripts/lp_rh_shadow_runner_v1_readonly.py` 与
`tests/test_lp_rh_shadow_runner_v1_readonly.py`。

### 1. 解析池态时间戳

按优先级取:
1. `pool_meta["as_of"]`(RFC3339)
2. `pool_meta["observed_at"]`(RFC3339)
3. pool_meta **文件的 mtime**(转成 UTC RFC3339)
4. 都拿不到 → `None`

`run_episode` 需要知道文件路径才能取 mtime。**先看它现在怎么拿到 pool_meta 的**
(daemon 传的是已解析的 dict 还是路径?看 `--pool-meta-json` 那条链路),
按既有惯例加一个可选参数传路径进来,**不要改变 pool_meta 的解析方式**。

### 2. 记进证据

在 `rh_economic_evaluations.cost_components_json` 里加(与 `leg_fraction` 同样的接法,
即独立关键字参数,**不要塞进 `_COST_COMPONENT_KEYS`**):
- `pool_state_as_of`:上面解析出的时间戳字符串,取不到就 `None`
- `pool_state_age_secs`:该步 `sample_time` 减去它,用 `_economic_str` 存;取不到就 `None`
- `pool_state_source`:`"AS_OF"` / `"OBSERVED_AT"` / `"FILE_MTIME"` / `"UNAVAILABLE"`

### 3. 让它出现在闸门原因里(**非阻断**)

当 `pool_state_age_secs` 超过阈值(新增模块级常量 `POOL_STATE_STALE_SECS = 21600`,即 6 小时),
往**循环内**的 `step_reasons` 追加一条 `POOL_STATE_STALE:<秒数取整>`。
取不到时间戳时追加 `POOL_STATE_AS_OF_UNAVAILABLE`。

**必须加在循环内的 `step_reasons`**(约 844 行 `conjunct_reasons=step_reasons` 那一处用到的列表),
因为只有它会经 `decision.reasons` 落进 `rh_gate_decisions.reasons_json`。
**循环结束之后再往 `steps[-1].conjunct_reasons` 追加是没用的** ——
那些行早就写完了,本项目已经因此出现过「fail-close 标记永远不落库」的缺陷。

**不要让它翻转任何闸位、不要让它阻断开仓。** 只是一条可见的原因码。
陈旧的池态是需要被看见的事实,但要不要因此停机是人的决定,不是这个包的决定。

## 不许动

- **不要修改、不要刷新 `reports/lp_rh/pool_meta.json`** —— 那是生产配置,动它是另一回事。
- 不要新增任何 RPC 调用、不要联网。
- 不要改 `_evidence_for` 的取值优先级、不要改任何成本数值或闸位判定。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要写 `reports/lp_rh/` 下的任何数据库;测试用 `tmp_path`,用仓库自己的 `migrate()` 建 schema。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试(≥6 条新增)

**写完把被测代码临时改坏,确认测试真的变红,再改回来。**
本项目已九次出现「测试构造的输入进不去被测代码」。

1. `pool_meta` 带 `as_of` → `pool_state_source == "AS_OF"`,age 计算正确
2. 只有 `observed_at` → `source == "OBSERVED_AT"`
3. 两者都没有但文件存在 → `source == "FILE_MTIME"`,age 用 mtime 算
4. 三者都拿不到 → `source == "UNAVAILABLE"`,`as_of`/`age` 都是 `None`(**不是 0**),
   且原因码里有 `POOL_STATE_AS_OF_UNAVAILABLE`
5. age 超过 6 小时 → `rh_gate_decisions.reasons_json` 里**确实查得到** `POOL_STATE_STALE:`
   (**断言要去查库,不要只断言内存对象** —— 这是本包最重要的一条)
6. age 未超阈值 → 原因码里**没有** `POOL_STATE_STALE`
7. 回归保护:所有既有成本数值与闸位判定**一个都没变**,陈旧也不阻断开仓

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`(12 万文件)。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q`(全绿)
2. `grep -n "POOL_STATE_STALE\|pool_state_as_of" scripts/lp_rh_shadow_runner_v1_readonly.py`
3. 报告里写明:你把原因码加在了哪一行,以及你如何确认那一处**会**落进 `reasons_json`
4. **不要跑全量测试**(另有 worker 并行跑,会撞车)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
