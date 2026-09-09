# RH-02az：把 PRD §21.1 的 7 项硬指标接进 Stage A 毕业闸门

## 背景：闸门形同虚设（独立审计已坐实）

`reports/AUDIT_stage_a_prd_reconciliation_20260909.md` 逐条核账结果：
**PRD §21.1（L1062–L1064）列了 9 条 Stage A 毕业条件，代码只检查了 2 条。**

| # | PRD 条件 | 代码是否检查 |
|---|---|---|
| 1 | 72 小时正向观测 | ✅ `stage_a_status:44-55` |
| 2 | 日历/异常的合成测试通过 | ❌ **根本没检查** |
| 3 | 关键字段真实生产 | ❌ **根本没检查**（实测 10 列全 NULL，fee_growth 仅 9.2% 非空）|
| 4 | 身份和能力证据清楚 | ❌ **根本没检查**（实测当前 CORE 池合约**无任何 attestation**）|
| 5 | 数据质量可计算 | ⚠️ 读了但不阻断 |
| 6 | RPC 预算可维持 | ❌ 只在展示区显示，未进判定 |
| 7 | 无不变量违反 | ❌ 被放在 `stage_b_status:74`，Stage A 完全放行 |
| 8 | 有效数据覆盖率 ≥99% | ✅ `stage_a_status:44-55` |
| 9 | 关键状态未知时新增模拟仓位=0 | ❌ **根本没检查** |

**后果**：等到 72 小时 + 99% 覆盖率那天，`stage_a["passed"]` 会变 True，
而 PRD 要求的另外 7 条一条都没验证过。**毕业是通往真钱的那道门。**

## 你要做的

改 `scripts/lp_rh_readiness_v1_readonly.py`，把缺失的条件接进 `stage_a_status`。

**核心原则：未知一律不通过。** 这个项目已确认 22 例「静默假绿」缺陷，
其中第 3、20 例正是「拿不到数据时当作通过」。任何一项拿不到证据，
必须让 `passed=False` 并在 `blockers` 里点名，**不得静默跳过、不得默认通过**。

### 逐条要求

1. **条件 3（关键字段真实生产）**：接入列健康检查。
   仓库已有 `scripts/lp_rh_column_health_v1_readonly.py`（**只 import 复用，不要重写**）。
   规则：`rh_market_states` 中**判定所需的关键列**非空率低于阈值 → 阻断。
   哪些列算「关键」由你从 PRD §21.1 上下文判断并在代码注释里写明理由；
   至少应包含 `reference_mid`、`sample_time`、`session`、
   `fee_growth_global_0`、`fee_growth_global_1`。
   阈值定为 **0.99**（与覆盖率同档），写成模块级常量并注明出处是本 spec。

2. **条件 4（身份和能力证据）**：断言**当前被观测的那个池**
   在 `rh_contract_attestations` 里有记录，且 `rh_pool_registry` 里该池的
   `token0`/`token1`/`fee`/`tick_spacing` 非空。
   **注意用 `asset_address` 过滤**（`RH-02aw` 已把 Stage A 改成按资产），
   不要全表统计。查不到 → 阻断，blocker 里点名缺哪一项。

3. **条件 6（RPC 预算）**：`budget_status`（`:114-118`）的结果接进判定，
   超预算 → 阻断。现在它只在展示区。

4. **条件 7（不变量违反）**：把 `invariant_violations` 从
   `stage_b_status` **复制**一份到 Stage A 的判定里（不要从 stage_b 删掉，
   那是 Stage B 自己的条件）。>0 → 阻断。

5. **条件 9（未知状态开仓数=0）**：查 `rh_gate_decisions` / `rh_shadow_positions`，
   断言不存在「`session` 为 UNKNOWN 或 health flags 非空时仍 granted」的记录。
   >0 → 阻断。若这两张表结构不支持这个查询，**在报告里说明**，
   并给出需要补什么列，**不要硬凑一个查不准的断言**。

6. **条件 2（合成测试通过）**：这一条**不要用「跑 pytest」实现**
   （闸门不该依赖测试运行器）。改为：要求一个**外部提供的证据输入**
   （例如 `synthetic_tests_passed: bool` 参数，由 CI 或调用方填），
   **缺失即阻断**。在 docstring 里写明这是「证据输入」而非「自检」。

### 输出结构

`stage_a_status` 的返回值里，每一条都要有独立可见的判定结果
（而不是揉成一个 bool），`blockers` 列表里用稳定的常量名，例如
`STAGE_A_KEY_FIELDS_INCOMPLETE`、`STAGE_A_POOL_NOT_ATTESTED`、
`STAGE_A_BUDGET_EXCEEDED`、`STAGE_A_INVARIANT_VIOLATIONS`、
`STAGE_A_UNKNOWN_STATE_POSITIONS`、`STAGE_A_SYNTHETIC_TESTS_UNKNOWN`。

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`（另一条线在改）、
`scripts/lp_rh_coverage_audit_v1_readonly.py`（刚验收入库）、
`scripts/lp_rh_column_health_v1_readonly.py`（只 import 复用）、任何 `.db`。
`tests/test_lp_rh_readiness_v1_readonly.py` **只允许新增测试**。

## 验收标准

1. **用真实库跑**（`reports/lp_rh/scanner.db`，资产
   `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`）：
   `stage_a["passed"]` 必须是 **False**，且 `blockers` 里**至少**出现
   `STAGE_A_POOL_NOT_ATTESTED`（审计实测当前池无 attestation 记录）。
   把完整的 blockers 列表贴进报告。
2. 每一条新接入的判定，都要有一条单测：**证据缺失时阻断**。
3. 每一条也要有一条单测：**证据齐备时不阻断**（防止过度拦截）。
4. **防回归**：时长与覆盖率两条既有判定的行为完全不变，
   用 `git show HEAD:scripts/lp_rh_readiness_v1_readonly.py` 加载旧版对照，
   在「其余条件都齐备」的输入下断言这两条的结果与旧版一致。
5. `graduation_verdict` 的传导不变：Stage A 未过时整体不得 PASS。
6. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4529 passed / 0 failed**，不得新增 failed。

## 坑（今晚刚踩过，别再踩）

- `reports/lp_rh/pool_meta.json` 里 `input_price_usd` 是**字符串** `"2484.0"`，
  取任何配置值都要显式转换并 fail-close。
- 测试至少要有一个用例用**真实的** `reports/lp_rh/scanner.db`，
  不要全用手写 fixture——今晚就有一个 worker 六个测试全绿而生产路径必崩。

## 纪律

- **不要执行任何 git 命令**。
- 不要重启 daemon，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件。
