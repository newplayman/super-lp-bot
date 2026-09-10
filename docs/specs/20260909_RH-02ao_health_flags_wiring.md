# RH-02ao：四个风险布尔从未接线，链降级闸门实际是空的

## 铁证（主脑用真实代码路径实测，不需要你重新调研）

`scripts/lp_rh_shadow_runner_v1_readonly.py:222-232` 调 `evaluate_health` 时传：

```python
halt=bool(sample.get("halt")),
corp_action_pending=bool(sample.get("corp_action_pending")),
sources_disagree=bool(sample.get("sources_disagree")),
chain_degraded=bool(sample.get("chain_degraded")),
oracle_heartbeat_secs=sample.get("oracle_heartbeat_secs") or 3600,
```

但 `load_samples_from_db` 放进 sample 的键**只有这 15 个**：

```
asset_address, chain_id, fee_growth_global_0, fee_growth_global_1,
health_flags_json, multiplier_human, oracle_paused, reference_age_secs,
reference_ask, reference_bid, reference_mid, sample_time, session,
source_event_time, source_payload_hash
```

**上面四个风险布尔一个都不在里面**，`sample.get(...)` 恒返回 `None`，
`bool(None)` 恒 `False`。实测：调真实的 `load_samples_from_db` 取 1991 条真实样本，
其中 **12 条** 的 `health_flags_json` 是 `["CHAIN_DEGRADED"]`，
而 `bool(sample.get('chain_degraded'))` 对这 12 条**全部是 `False`**。

后果：`market_and_chain_risk_pass` 这个 conjunct **在任何情况下都不会因
链降级、交易暂停、公司行动、数据源分歧而失败**，实际只剩 `oracle_paused`
和时效性两个维度在起作用。**风险闸门大部分是空的。**

（交接文档 HANDOFF_20260909_3_CN.md §1 写「唯一失败者是 CHAIN_DEGRADED 样本，
正确拦住」——那是**误归因**，那一步失败另有原因。不要相信那句话。）

## 你要做的

`health_flags_json` 是采集器写入的 JSON 字符串数组，例如 `["CHAIN_DEGRADED"]`。
在 `load_samples_from_db` 里把它**解析成布尔**，放进 sample：

1. 解析 `health_flags_json`（可能是 `None`、`""`、合法 JSON 数组、或损坏字符串）；
2. 映射到 sample 的键：
   - `"CHAIN_DEGRADED"` → `chain_degraded=True`
   - `"HALT"` → `halt=True`
   - `"CORP_ACTION_PENDING"` → `corp_action_pending=True`
   - `"SOURCES_DISAGREE"` → `sources_disagree=True`
   - 先 `grep -rn 'CHAIN_DEGRADED\|SOURCES_DISAGREE\|CORP_ACTION' scripts/ | head -20`
     确认采集器实际写入的**字面量拼写**，以采集器为准，不要照抄我上面的猜测；
3. **失败关闭**：`health_flags_json` 为 `None` 或空字符串 → 四个布尔都是 `False`（这是正常情况，
   表示采集时没有异常）；但**JSON 解析失败**或**出现未知 flag** →
   该样本必须让 `market_and_chain_risk_pass` **失败**，
   理由里点名是哪个 flag 不认识（未知风险 ≠ 无风险）。
4. `oracle_heartbeat_secs` 保持现状（`or 3600` 有明确默认语义），不要动。

## 不许动

`scripts/lp_rh_v3_inventory_v1_readonly.py`、`scripts/lp_rh_pnl_v1_readonly.py`、
任何 recorder / daemon、任何 `.db`、`pool_meta.json`。
**特别注意**：`run_episode` 里的 NAV / accrual 块**另有一条线在改**，
你只碰 `load_samples_from_db` 与 `compute_conjuncts` 里读这四个键的地方，
**不要碰第 356–400 行那段 NAV / hodl 代码**。

## 验收标准

1. 用真实 DB 实测并贴出输出：调 `load_samples_from_db`，
   断言那 12 条 `["CHAIN_DEGRADED"]` 样本的 `sample["chain_degraded"] is True`。
2. 单测（合成样本）：`health_flags_json='["CHAIN_DEGRADED"]'` 的样本
   → `market_and_chain_risk_pass` 为 False，且失败理由里出现该 flag。
3. 单测：`health_flags_json=None` 与 `'[]'` → 四个布尔均 False，
   该 conjunct 不因此失败（正常样本不得被误伤）。
4. 单测：`health_flags_json='{ 坏的 json'` → 该 conjunct 失败，理由点名解析失败。
5. 单测：`health_flags_json='["SOMETHING_NEW"]'`（未知 flag）→ 该 conjunct 失败。
6. `/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q -p no:cacheprovider`
   全绿；全量测试贴尾部供主脑判读（另一条线在改同文件别处，红了先注明再说）。

## 纪律

- **不要执行任何 git 命令**。
- 单次 Write/Edit ≤ 150 行或 6000 字符。
- 不要整读 >300 行的文件，用 `sed -n 'a,bp'`。
- 不要重启 daemon / 录制器，不要动 crontab。

---

## ★主脑 2026-09-10 01:0x 追加：缺陷已复核仍在，且 shadow_runner 已被大改★

本 spec 写于 09-09 晚，中间 `shadow_runner.py` 经历了多轮改动
（`12efd38` fee 量纲、`9c59e2e` 市价重估、`8b69b7c` quote provenance）。
**动手前主脑已复核，缺陷仍在**：

```
loader 返回 1999 条样本
chain_degraded / halt / corp_action_pending / sources_disagree
  —— 四个键在 sample 里全部不存在，bool(get()) 恒 False
带 CHAIN_DEGRADED 的真实样本 6 条，闸门读数全是 False
```

### 与当前代码的衔接

- `load_samples_from_db` 现在已经把 `health_flags_json` 放进 sample（原样字符串）。
  你要做的是**解析它**并映射成那四个布尔。
- `compute_conjuncts` 里调 `evaluate_health` 的那几行现在在 **`:306-313`** 附近
  （行号已变，用 `grep -n 'evaluate_health' scripts/lp_rh_shadow_runner_v1_readonly.py` 定位）。
- **不要碰** `run_episode` 里 NAV / hodl / quote 那一段——那是今晚三轮修复的成果，
  与本包无关。你只改「读风险布尔」这条路径。

### 落地后扫描器基线会变

`scripts/lp_silent_failure_lint_v1_readonly.py` 的基线按 `文件:行号` 匹配，
你改了 `shadow_runner.py` 会让后面的命中整体位移、被判成「新增」。
**这是已知的误报，不要为此修改扫描器或基线** ——
主脑验收时会用 `--write-baseline` 刷新。
但你要在报告里说明：**规则 2 那 5 条命中（`bool(sample.get(...))`）
应当在你修完后消失**，因为那正是本包要修的东西。若它们还在，说明没改到位。

### 验收补充

除原有标准外，加一条：修完后跑
```bash
/root/lp-bot/.venv/bin/python scripts/lp_silent_failure_lint_v1_readonly.py --json \
  | /root/lp-bot/.venv/bin/python -c "
import sys,json
d=json.loads(sys.stdin.read()); h=d if isinstance(d,list) else d.get('hits',[])
bad=[x for x in h if x.get('file','').endswith('lp_rh_shadow_runner_v1_readonly.py')
     and str(x.get('rule') or x.get('rule_id'))=='2']
print('shadow_runner 剩余规则2命中:', len(bad))
for x in bad[:5]: print(' ', x.get('line'), x.get('snippet'))"
```
**期望 0 条**（原本 5 条）。把输出贴进报告。

全量基线是 **4649 passed / 0 failed**。
