# RH-02bd：第二轮独立审查的跟进（五条，两条是主脑引入的）

完整证据：`reports/REVIEW_tonight_fixes_round2_20260909.md`。
审查对 7 个 commit 给出 2 个 ACCEPT、5 个「需修补」。**主脑已逐条复核，判定成立。**

## 一、★地址大小写敏感 —— 合法地址被判成「无数据」★（最高优先级）

`scripts/lp_rh_coverage_audit_v1_readonly.py:223-226` 与
`scripts/lp_rh_readiness_v1_readonly.py:344-346` 按**大小写敏感**比较 `asset_address`。

实测：库里是小写（9727 行），传入 `asset.upper()` 返回 `NO_ASSET_DATA`、0 行。
**EVM 地址有 EIP-55 checksum 大小写形式，两种写法指的是同一个地址。**
一个合法调用方传 checksum 形式，就会得到「这个资产不存在」——
而 `RH-02aw` 特意让 `NO_ASSET_DATA` 阻断 Stage A，于是**合法输入被判永不毕业**。

修：查询统一用 `LOWER(asset_address) = LOWER(?)`，
**同步改 key-health 与 MIN/MAX 查询**（审查点名这几处都要改）。
加测试：同一地址的小写 / 大写 / checksum 三种写法结果一致。

## 二、★Stage A 闸门实际永久关闭★

`stage_a_status()` 本身没问题——直接传全证据可以通过。
但**真实 dashboard 路径拿不到 `invariant_violations`**：

- `_build_state` 声明了该参数（`:494-496`）
- CLI 只解析并传 `synthetic_tests_passed`（`:577-585`）
- **仓库里没有任何生产调用方提供 `invariant_violations`**
- 于是 `invariant_violations=None` 必然触发 `STAGE_A_INVARIANT_VIOLATIONS`

**「未知即阻断」是对的，但必须有拿到证据的途径**，否则闸门不是严格，是焊死。

修：新增一个**只读**的 invariant 审计函数（放 `scripts/` 下新文件或复用既有审计），
由 `_build_state` 调用并把结果传进 `stage_a_status`。
它至少要能回答「当前库里有没有可检测的不变量违背」。
若某类不变量暂时无法检测，**返回明确的「未知」并保持阻断**，但要在 dashboard 里
写清是哪一类未知——让人知道该补什么，而不是只看到一个红灯。

## 三、quote 缺失静默默认 1.0

`scripts/lp_rh_shadow_runner_v1_readonly.py:381-385`：
`raw_quote` 在 pool_meta 与 sample 都缺失时回退 `DEFAULT_QUOTE_USD_PER_TOKEN1`（1.0）。
**真实 `pool_meta.json` 里就没有 `quote_usd_per_token1`**，所以生产路径一直走默认。

PRD:651 明确写了 USDG 不许强制按 $1 估值。这是第 6 类（宽容默认值）。

修：quote 缺失时 `open_valid=False`（该步无 NAV / 无 hodl），
与缺 range_pct / price 同等处理。
**注意**：这会让当前真实数据的 NAV 全部变 None ——
所以**同时**要在 `reports/lp_rh/pool_meta.json` 里补一条显式证据。
但**你不要改那个文件**（它是生产配置，由主脑决定）；
你只改代码 + 测试，并在报告里写明「落地后需要给 pool_meta 补 quote_usd_per_token1」。

## 四、dec0/dec1 缺失时默认 18/6

同一处（`:379-380`）。修法同上：position valuation 要求 decimals 显式存在，缺失 fail-close。
（这一条影响面小，因为 pool_meta 里 dec0/dec1 确实存在。）

## 五、budget 的 WARN 是否该阻断

`scripts/lp_rh_readiness_v1_readonly.py:165-167` 对 `state != "OK"` 阻断，
于是 `WARN`（仍低于 100% 软预算）也阻断。
PRD 说的是「RPC 预算可维持」。

修：**只对 `OVER` 阻断**，`WARN` 记入 dashboard 但不阻断；
在代码注释里写明这个政策选择的依据。加两条测试分别锁 WARN 与 OVER 的行为。

## 六、容差的真正根因（主脑诊断错了，一并修正）

主脑把容差从 `1e-20` 放宽到 `1e-12`，理由写的是「Decimal 28 位精度不可达」。
**审查核算后这个理由不成立**：
- 测试 oracle 用的是 **float 版** `position_liquidity_raw`，runner 用的是 **Decimal 版**
  `inventory_for_position`，两者相对误差实测 `1.1117e-15` —— 这才是误差来源；
- 若 oracle 也用 Decimal 版，误差约 `1.83e-22`，**原来的 `1e-20` 实际可达**。

修：把 `tests/test_lp_rh_fee_accrual_dimensional_v1_readonly.py` 与
`tests/test_lp_rh_first_step_accrual_v1_readonly.py` 里的手算 oracle
**改用 Decimal 版 `inventory_for_position`**（与 runner 同一个实现来源），
然后把 `NAV_DIFF_REL_TOL` 收紧回 `1e-20`，并更新注释说明真实根因。
若收紧后仍红，**贴出实测误差**，不要再放宽——先说清为什么。

## 不许动

`reports/` 下任何文件（含 `pool_meta.json` 与所有报告）、任何 `.db`、
`scripts/lp_rh_pool_attestation_backfill_v1.py`。

## 验收标准

1. 大小写：同一地址三种写法（小写 / 大写 / EIP-55 checksum）
   在 `coverage_for_asset` 与 `_build_state` 下结果**完全一致**，把三组实测贴进报告。
2. invariant 证据：`_build_state` 走真实库时，
   `STAGE_A_INVARIANT_VIOLATIONS` **不再因「没人提供」而出现**
   （若确实检测到违背则应出现，把实测 blockers 贴进报告）。
3. quote / decimals 缺失 → 该步无 NAV，且理由可见。
4. budget：`WARN` 不阻断、`OVER` 阻断，各一条测试。
5. 容差收紧回 `1e-20` 后测试仍绿；贴出改用 Decimal oracle 后的实测误差。
6. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4602 passed / 0 failed**，不得新增 failed。

## 纪律

- **不要执行任何 git 命令**（`git show` 只读可用）。
- 不要重启 daemon，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行。
