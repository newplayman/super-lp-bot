# RH-02ax：清除剩余 10 个模块级 Decimal 精度污染源

## 背景

`RH-02ah`（commit `5efcde5`）已清掉 RH 线的三个污染源
（`lp_rh_exit_depth` 的 `prec=80`、`lp_rh_organic_recorder` 与
`lp_rh_premium_recorder` 的 `prec=60`），改法是把需要高精度的计算包进
`with localcontext() as ctx: ctx.prec = N`。

**但还剩 10 个**（都在 BSC / strategy 线上），它们在 import 时把全局
`getcontext().prec` 改掉，于是全量测试跑起来时环境精度是 60 而不是默认 28：

```
scripts/lp_base_m1_c5_dry_run_v1_readonly.py
scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py
scripts/lp_bsc_fee_velocity_smoke_v1_readonly.py
scripts/lp_bsc_pancakeswap_v3_precise_quote_v1_readonly.py
scripts/lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py
scripts/lp_bsc_quoter_staticcall_amount_fix_v1_readonly.py
scripts/lp_bsc_realdata_economics_with_recovered_fee_v1_readonly.py
scripts/lp_precise_quote_pipeline_v1_readonly.py
scripts/strategy_evidence_r4b_active_liquidity_replay.py
scripts/strategy_evidence_r4c_independent_clmm_liquidity_replay.py
```

实害已经发生过一次：`tests/test_lp_rh_v3_inventory_v1_readonly.py` 的两条
精度测试在全量跑时报 `assert 60 == 28`——**任何新写的 Decimal 测试都会
随机踩到这个**。

## 你要做的

对上面 10 个文件，逐个：

1. `from decimal import ... getcontext` → 视情况改成 `localcontext`
   （若文件别处还用到 `getcontext` 的其它功能就都保留）；
2. 删掉模块级的 `getcontext().prec = N`；
3. 把该文件里**真正需要高精度的计算块**包进
   ```python
   with localcontext() as ctx:
       ctx.prec = N        # N 用该文件原来设的那个值，不要改数值
       ...计算...
   ```
   **在 with 块内部把结果定型**（`return` 或 `+x`），不要让未定型的中间值漏到块外。
   参考已完成的改法：`sed -n '110,125p' scripts/lp_rh_exit_depth_v1_readonly.py`。
4. 判断哪些块需要包：涉及 `sqrt`、大整数相除、`10**decimals` 缩放、
   Q96/Q128 定点换算、bps 换算的都要；纯加减和比较不需要。

**逐个文件改、逐个验证，不要 10 个一起改完再跑测试。**

## 硬性要求：数值行为一律不得改变

这 10 个文件都有既有产物和测试。**你的改动必须是纯粹的精度作用域重构，
不得改变任何计算结果。** 每改完一个文件，用下面这段做自证（把输出贴进报告）：

```bash
/root/lp-bot/.venv/bin/python -c "
from decimal import getcontext
b = getcontext().prec
import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')
import scripts.<模块名>
print('<模块名>', b, '->', getcontext().prec)"
```

**两个数必须都是 28。**

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`、
`scripts/lp_rh_exit_depth_v1_readonly.py`（两条线正在改这两个文件，碰了就冲突）、
任何 `scripts/lp_rh_*`（RH 线的三个已经改完了）、任何 `.db`、`pool_meta.json`、
任何既有测试文件（**只允许新增测试**）。

## 验收标准

1. `grep -rln '^getcontext()\.prec\|^ *getcontext()\.prec *=' scripts/*.py` **无输出**。
2. 上面那段自证脚本对 10 个模块**全部输出 `28 -> 28`**，逐个贴进报告。
3. 全量测试：`/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3`
   **基线是 10 failed / 4503 passed**，10 个红全部在
   `test_lp_rh_fee_growth` / `test_lp_rh_first_step_accrual` / `test_lp_rh_loader_fee_growth`
   这三个文件里（另一条线正在改 fee 公式，与你无关）。
   **你不得新增任何 failed**，也不要去碰那三个文件。
4. 新增一条测试（放在新文件 `tests/test_no_module_level_decimal_pollution_v1_readonly.py`）：
   遍历 `scripts/*.py`，断言没有任何模块级 `getcontext().prec = ` 赋值。
   这是防复发的锁——用源码扫描（`ast` 或正则皆可），不要 import 它们。

## 纪律（违反即退回）

- **不要执行任何 git 命令**（不 add、不 commit、不 stash、不 checkout）——入库是主脑裁决后的动作。
- 不要重启任何 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件，用 `sed -n 'a,bp'` 读片段。
- 命令输出只贴尾部。

## 报告要写清

- 10 个文件各包了几处 `localcontext`；
- 10 段自证脚本的原样输出；
- 全量测试的原样尾部；
- `git status --short | grep -v '^??'` 的原样输出（应只有你改的那 10 个文件 + 1 个新测试）。
