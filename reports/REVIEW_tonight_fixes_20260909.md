# 一、假测试（若有）

按题目“回退后仍绿”定义，以下新增测试对本次修复没有变异鉴别力：

| commit | 测试函数 | 为什么回退修复它也不红 |
|---|---|---|
| dd00d1a | `tests/test_lp_rh_premium_guard_v1_readonly.py:203` `test_freshness_positive_age_regression` | 只覆盖过去时间戳；父版本本来就返回相同的 FRESH/STALE。 |
| dd00d1a | `tests/test_lp_rh_premium_guard_v1_readonly.py:216` `test_freshness_none_sentinel_not_confused_with_negative_age` | `None` 和 1 秒未来时间戳在父版本也满足断言。参数化未来时间测试整体有效，因为 10 秒、3600 秒 case 会红；3/5 秒 case 本身无效。 |
| 7e5052a | `tests/test_lp_rh_meme_audit_v1_readonly.py:117` `test_holder_evidence_available_true_passes` | 父版本对 `{"available": True}` 也放行。 |
| 7e5052a | `tests/test_lp_rh_meme_audit_v1_readonly.py:123` `test_holder_evidence_available_false_is_rejected` | 父版本同样返回 `HOLDER_CONCENTRATION_EVIDENCE_MISSING`。 |
| 7e5052a | `tests/test_lp_rh_meme_audit_v1_readonly.py:131` `test_holder_evidence_verified_true_passes` | 父版本对 `{"verified": True}` 也放行。 |
| 456ab04 | `tests/test_lp_rh_pnl_v1_readonly.py:288` `test_replay_explicit_zero_external_flow_remains_valid` | 显式零在父版本也返回 `net_pnl == "10"`。 |
| 6399aa0 | `tests/test_lp_rh_gas_reserve_v1_readonly.py:271` `test_normal_native_gate_result_is_unchanged` | 正常输入父版本结果完全相同。 |
| 6399aa0 | `tests/test_lp_rh_gas_reserve_v1_readonly.py:286` `test_normal_exit_requirement_is_unchanged` | 正常输入父版本结果完全相同。 |
| 6399aa0 | `tests/test_lp_rh_gas_reserve_v1_readonly.py:293` `test_normal_wrapped_result_is_unchanged` | 父版本本来就忽略余额并返回相同结构。 |

核心缺陷测试均有效：父版本分别把未来 10/3600 秒判为 FRESH、空 evidence 放行、缺失 calldata claims 判为匹配、缺失外部流记成 `100`、`None` 计数放行，以及 Infinity 余额放行。

# 二、修复引入的新问题

| 文件:行号 | 问题 | 触发输入 | 建议 |
|---|---|---|---|
| `scripts/lp_rh_pnl_v1_readonly.py:221-239` | 只把“键不存在”视为缺失；JSON 常见的 `null` 仍进入 `Decimal(None)` 并抛异常。 | `_replay_step("t1", "1100", external_net_flow=None)` | 将“键不存在或值为 None”统一视为不可用，并沿用 `net_pnl=None + reason`。归因字段也应同样处理。 |
| `scripts/lp_rh_readiness_v1_readonly.py:148-169` | 新增的严格 LIVE 状态检查会把畸形 truthy 值判为 FAIL，但授权提示为空。 | `graduation_verdict({"passed": True}, {"passed": True}, {"blockers": [], "live_allowed": "yes"})` 返回 `verdict="FAIL"`、`explicitly_not_authorized=[]`。 | `explicitly_not_authorized` 也使用 `live_gate.get("live_allowed") is not True`，或先校验字段必须是 bool。 |
| `scripts/lp_rh_gas_reserve_v1_readonly.py:255-275` | `wrapped_does_not_count` 文档声明 WETH 余额被忽略，但修复后它变成必需且必须合法。 | `wrapped_does_not_count(weth_balance_wei=None, native_balance_wei=0)` 现在失败。 | 该函数只校验 native balance，或明确把 WETH 缺失视为不影响结论。 |
| `scripts/lp_rh_gas_reserve_v1_readonly.py:61-69,271-275` | `wrapped_does_not_count` 的失败结果新增 `pass`/`reason`，正常结果没有这两个字段，返回结构不稳定。 | 正常输入没有 `result["pass"]`；非法 WETH 输入有 `pass=False`。 | 固定统一 schema，或失败统一返回 `None`/明确的同构结果。 |

readiness 的 bool 排除本身没有发现合法调用方被误伤：生产 `_build_state` 在 `scripts/lp_rh_readiness_v1_readonly.py:271-273` 传入的是整数 `0`，仓库没有生产代码传入 bool 计数。把 `True/False` 当计数拒绝是合理的。

新增代码没有引入新的 `.get(key, default)`；性能上只有常数级校验，gas 函数虽重复做了一次 Decimal 转换（`100-128`、`147-209`），对 15 分钟调用一次的路径不构成明显开销。

# 三、重复实现清单

有多处：

| 文件:行号 | 实现 | 是否一致 |
|---|---|---|
| `scripts/lp_rh_v3_inventory_v1_readonly.py:75-92,151-175` | 新增模块内部的入场两腿和市价重估公式 | 两套公式数学上一致，属于同一模块内的重复表达。 |
| `scripts/lp_v3_fee_share.py:3-17` | `position_liquidity_raw` | 在 `quote_usd_per_token1 == 1` 时与 RH Decimal 实现相同；标准输入下新实现为 `205043081922807.992...`，旧 float 实现为 `205043081922808.22`。非单位 quote 不一致，例如 quote=`0.99` 时新实现为 `207114224164452.517...`，旧函数仍为 `205043081922808.22`。 |
| `scripts/lp_il_inventory_engine_v1_readonly.py:95-103,157-173` | 资本换算 liquidity、当前两腿数量 | 与 RH 实现的 human-unit V3 公式一致，但使用 float，且没有 quote/decimals raw 语义。 |
| `scripts/lp_il_math_replay_v1_readonly.py:177-203` | 独立 reference entry/inventory | 与 `lp_il_inventory_engine` 和 RH 实现一致；这是第三处实际重复实现。 |
| `scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py:247-306` | 独立计算 `L_position` 和两腿 | 不一致：强制 50/50 分仓（`273-275`），并对 tick range 做取整；不是实际 V3 两腿。 |
| `scripts/lp_base_m1_c5_dry_run_v1_readonly.py:93-101,158-159` | 根据池子 liquidity 计算 active notional，并按 50/50 构造 mint 数量 | 不一致：这是当前池 active liquidity/合成 50/50 输入，不是实际仓位 inventory。 |

`strategy_evidence_r4b_active_liquidity_replay.py:159-322` 虽有另一套公式草稿，但函数最终只有 `pass`，不产生实际结果。

# 四、总体判断

| commit | 判断 | 理由 |
|---|---|---|
| dd00d1a | ACCEPT | 未来时间戳的核心回归测试有效，修复逻辑正确。 |
| 7e5052a | ACCEPT | 空对象、无支持字段和非 bool evidence 均正确拒绝。 |
| 8da175a | ACCEPT | 两个缺失 claim 场景均能捕获父版本的误放行。 |
| 456ab04 | 需修补 | 缺失键已修复，但 `None` 仍会抛异常。 |
| 74ff992 | 需修补 | 缺失计数已 fail-closed，但畸形 truthy `live_allowed` 的授权提示不一致。 |
| 6399aa0 | 需修补 | Infinity/NaN 闸门已修复，但错误校验了声明无关的 WETH，且失败 schema 不稳定。 |
| 805dc35 | ACCEPT | V3 市价重估数学和边界逻辑正确；按提交范围仅提供函数，未负责接线。 |
| 3ad02ec | ACCEPT | Decimal 入场两腿推导正确并显式要求 quote；重复实现风险已列入一致性清单。 |

`pytest` 在当前只读沙箱因没有可用临时目录无法启动；以上结论来自指定解释器加载父提交源码后的内存变异重放及直接数值验证，未修改任何文件。