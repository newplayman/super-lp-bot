# 三条结论

| 疑点 | 坐实/证伪 | 一句话依据 |
|---|---|---|
| 一 | 坐实（当前数据未触发） | 查询未按 `asset_address` 分组；未来并行资产会把样本数相加，覆盖率被高估。 |
| 二 | 坐实（当前数据未触发，未来可构造触发） | 缺字段时可构造零值 PoolKey；声明的 `pool_id` 等于该哈希即可错误得到 `ATTESTED_SAME_BLOCK`。 |
| 三 | 坐实（当前无上游调用，但直接输入可触发） | `Infinity` 被转成 `Decimal` 并标记为可行动区间；当前语义把未知上限表示为 `None`，不是 Infinity。 |

# 逐条证据

## 一、覆盖率未按资产过滤

数据查询时：

- `rh_market_states` 只有 1 个资产：
  - `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`
  - 9102 行
  - `2026-09-08T05:15:14.435446Z` 至 `2026-09-09T20:26:42.576250Z`
  - 时间跨度约 39 小时 11 分 28 秒
- `scripts/lp_rh_coverage_audit_v1_readonly.py:226-227` 查询全部 `sample_time`，没有 `WHERE asset_address=...`。

用现有样本按时间交错分为两个虚拟资产：

- 虚拟 A：4551 行，覆盖率 `0.4838915`
- 虚拟 B：4551 行，覆盖率 `0.4838915`
- 未过滤合并计算：`0.9676802`
- 合并结果约为单资产平均值的 `1.9998` 倍。

这说明两个资产各自只有约 48.4% 采样率时，合并后会被错误显示成约 96.8%。若两个资产都各自拥有当前完整样本流，则单资产约 `0.96768`，未过滤合计约 `1.93536`，会直接越过 `0.99` 阈值。

Stage A 的路径是：

- `scripts/lp_rh_readiness_v1_readonly.py:247-254`：对整个 `rh_market_states` 做 `MIN/MAX/COUNT`，并传给 `stage_a_status`
- `stage_a_status` 的返回值 `["coverage_ratio"]` 和 `["passed"]` 在 `:75-83`
- `graduation_verdict` 在 `:156` 读取 `stage_a.get("passed")`

因此，覆盖率高估会直接使 Stage A 的 `passed` 变为真；整体毕业仍需 Stage B 和 live gate 同时通过。当前数据本身仍未毕业：时间只有约 39.19 小时，且 Stage A 覆盖率约 `0.96769`。

修法要点：Stage A 和 coverage audit 都必须绑定明确的 `asset_address`；若支持多资产，应逐资产计算并要求目标资产分别通过，禁止把多资产行数直接相加。

## 二、V4 合成 PoolKey 相撞

触发条件：

1. 候选只有合法 32 字节 `pool_id`，没有 20 字节 `pool`，从而被 `dispatch_protocol` 判为 V4。
2. 缺少 `currency0`、`currency1`、`tick_spacing`、`hooks` 时，代码分别落成零值：
   - 两个 currency 为零 bytes32
   - `tick_spacing=0`
   - `hooks=0x000...000`
3. 本地存在 Keccak 实现。
4. 声明的 `pool_id` 恰好等于该合成 key 的哈希。

具体输入：

```python
{
    "pool_id": "0x16ba7f990509be07e4c437e2d93917ae094d98f39d0adb8f5539fd728be9d3fc"
}
```

实际结果：

```text
protocol: v4
pool_key:
  currency0: None
  currency1: None
  tick_spacing: 0
  hooks: 0x0000000000000000000000000000000000000000
attestation_status: ATTESTED_SAME_BLOCK
```

对应代码为 `scripts/lp_rh_pool_probe_v1_readonly.py:113-122`、`:261-274`。

当前库没有 V4 池：

- `rh_pool_registry`：1 行，`protocol='v3'`，`pool_id` 为 NULL
- `rh_contract_attestations`：387 行，`policy_version='v1'`、`abi_version=NULL`
- `rh_contract_attestations` 没有 `protocol` 列，且 `evidence_json` 中没有 V4 标记

所以当前数据不会触发；将来接入 V4 后，如果上游把缺字段候选送入该函数，并且 `pool_id` 是按同一错误逻辑生成的，就会触发错误 attestation。若上游提供真实完整 V4 PoolKey，则当前代码反而还遗漏了 `fee` 字段（`:106-110`），更可能产生错误的 `UNVERIFIED`。

修法要点：缺少任一必需字段时 fail-closed；V4 ABI 编码必须包含 `currency0、currency1、fee、tickSpacing、hooks`，并校验 `pool_manager` 与字段格式。

## 三、`size_interval` 接受 Infinity

仓库内调用方：

```text
scripts/lp_rh_size_interval_v1_readonly.py:54
scripts/lp_rh_size_interval_v1_readonly.py:158
```

除该模块自己的 CLI 外，没有其他 `scripts/` 调用方；测试调用已排除。`rh_economic_evaluations` 当前也是 0 行。因此当前没有 RPC、配置或计算结果能把 Infinity/NaN 传入该模块。

但直接输入可以触发：

```python
size_interval(q_min="0", q_max="Infinity")
```

实际结果：

```text
status = COMPUTED
q_max = Decimal("Infinity")
width = Decimal("Infinity")
is_actionable(...) = True
```

`NaN` 则会在比较 `lo > hi` 时抛出 `decimal.InvalidOperation`。

当前语义不支持 Infinity 作为“无上限”：

- PRD §6.4 的 `q_max` 是多个风险上限的 `min(...)`
- `scripts/lp_rh_exit_depth_v1_readonly.py:347-361` 明确规定无法证明退出上限时返回 `None`
- `docs/specs/20260908_RH-05c_exit_depth_quote.md:32` 明确写明无数据返回 `None`，不是 0、不是无穷
- `docs/specs/20260909_RH-03e_size_interval_empty.md:20` 也把 `None` 定义为缺失输入

所以 Infinity 不是当前语义下的合法特性，而是输入校验缺陷；只是当前仓库没有上游调用，因此尚未在生产数据链路触发。

修法要点：`_to_decimal` 转换后必须检查 `is_finite()`；Infinity/NaN 返回明确的非法输入或 `INPUTS_UNAVAILABLE`，不得进入 `COMPUTED` / `SIZE_INTERVAL_POINT`。

# 顺带发现

无