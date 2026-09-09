# RH-08e：Stage A 除覆盖率外五项门槛的取证（**只取证，不下判定**）

## 背景

Stage A 的覆盖率门槛已单独核算（`STAGE_A_COVERAGE_FORECAST_20260909.md`：
72 h 时约 98.78%，需约 90 h 才达 99%）。但 PRD §21.1 还有**五项其他要求**，
至今**没有任何一项被单独核验过**：

> 至少 72 小时正向观察作为初始门槛，并通过**日历／异常的合成测试**。需要：
> **关键字段真实生产**、**身份和能力证据清楚**、**数据质量可计算**、
> **RPC 预算可维持**、**无不变量违反**。

**不要等到 90 小时才开始查**——如果某项现在就不达标，越早发现越好。

## 与审计包同样的纪律

**产物中不许出现 PASS / FAIL / 通过 / 达标 这类判定词**，出现即不合格。
你只摆证据，判定由主脑做。**查不出来就如实写查不出来**，
那是有价值的结论；编一个勉强沾边的证据才是失败。

## 唯一产物

`reports/rh_pivot/20260907T124500Z/STAGE_A_GATES_EVIDENCE.json`

一个 JSON 对象，五个键，每个形如：

```json
{
  "key_fields_produced": {
    "checks": [
      {"claim": "rh_market_states.reference_mid 有真实 writer 且非恒 None",
       "method": "sqlite 查询 reports/lp_rh/scanner.db",
       "command": "select count(*), count(reference_mid) from rh_market_states",
       "output": "5069|5062",
       "observation": "5069 行中 5062 行有值，7 行为 NULL"}
    ],
    "unresolved": ["说不清的地方，如实列出"]
  }
}
```

五个键：`key_fields_produced` / `identity_and_capability_evidence` /
`data_quality_computable` / `rpc_budget_sustainable` / `no_invariant_violations`。

## 每一项要查什么

1. **关键字段真实生产**：对 `rh_market_states` 与 `rh_source_snapshots` 的每一列，
   统计非 NULL 行数与不同取值个数。**特别注意「有值但恒为同一个值」的列**
   ——本项目已发现 `session` 被硬编码成 `"UNKNOWN"`（4361 行全同），
   这类列看着有数据其实没有信息。逐列报出 `distinct_count`。
2. **身份与能力证据**：`rh_contract_attestations` 与 `rh_assets` 有多少行、
   覆盖多少个地址、`chain_id` 取值分布。**证据是否为空是关键结论之一。**
3. **数据质量可计算**：`rh_market_states` 的 `health_flags_json` 与
   `reference_age_secs` 的分布；有多少行能算出质量、多少行算不出。
4. **RPC 预算可维持**：`rh_rpc_health` 的 provider/method/state 分布，
   以及 `reports/lp_rh/*.db` 的总字节数对 2 GiB 软预算的占比。
   `scripts/lp_rh_store_v1_readonly.py` 有 `budget_status`，**调用它并记录返回值**。
5. **无不变量违反**：跑
   `/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`
   并把**尾部原样**记进 `output`；另外 grep 六个受保护常量
   （`STABLE_MIN_FRAC` `NETCOVER_SHADOW` `NETCOVER_TINY_LIVE` `POSITION_TVL_SHARE`
   `HARD_POSITION_TVL_SHARE` `LVR_COEFFICIENT_MODEL`）的当前值并逐个记录。

## 硬约束

**只读。不改任何文件，不写任何库。** 只新建上面那一个 JSON。不联网。
所有 `command` 字段必须是**你真正执行过的命令**，`output` 必须是**原样输出**
（可截断，但不得改写）。单次 Write ≤150 行或 6000 字符，分次写。
写完 `python -c "import json;d=json.load(open(...));print(sorted(d))"` 自检，
应打印那五个键。

## 验收
```
python -c "import json;d=json.load(open('reports/rh_pivot/20260907T124500Z/STAGE_A_GATES_EVIDENCE.json'));print(sorted(d));print({k:len(v.get('checks',[])) for k,v in d.items()})"
git diff --stat
```
第一条应打印五个键与各自的检查条数（每项 ≥3 条）；
`git diff --stat` 必须为**空**。两条命令原样输出贴回。
