# RH-02bb：`position_liquidity_raw` 缺 quote 参数，导致建仓与计费口径撕裂

完整证据：`reports/AUDIT_duplicate_v3_inventory_20260909.md` 第四节。

## 问题

`scripts/lp_v3_fee_share.py:3` 的
`position_liquidity_raw(size_usd, entry_price, range_pct, dec0=18, dec1=6)`
**没有 quote 参数**，隐含假设「1 token1 = 1 USD」。

实测：`quote=0.99` 时正确的 `L_pos` 应为 `207114224164452.517`，
它仍返回 `205043081922808.22`，**低估约 1%**，手续费分摊被系统性低估。

### 最要紧的一处：同一段代码里两个口径

`scripts/lp_rh_shadow_runner_v1_readonly.py:391` 建仓时**不传 quote**，
而同一个函数在 `:402` 附近折算手续费为 USD 时**乘了 quote**。
**建仓按「1 token1 = 1 USD」，计费按真实 quote——口径撕裂。**

### 一个调用方已经自己打了补丁

`scripts/lp_netcover_inputs_v1_readonly.py:604-608` 在调用前先做
`position_quote = size_usd / float(quote_usd)` 再传进去。
**调用方替函数补了它缺失的能力**——这本身就是该把能力放回函数里的证据，
否则每个调用方都要记得打这个补丁，而现在有 5 个没打。

## 你要做的

1. `position_liquidity_raw` 增加关键字参数
   `quote_usd_per_token1: float = 1.0`，在函数内部把 `size_usd` 换算到 quote 计价
   （即 `size_quote = size_usd / quote`），**默认 1.0 保持现有调用方行为完全不变**。
   quote `<= 0` 或非有限 → 返回 `0.0`（该函数既有的失败表达就是返回 0.0，照抄）。
2. `scripts/lp_rh_shadow_runner_v1_readonly.py:391` 建仓处**显式传入它已经算好的 `q`**
   （同一个函数里 `:402` 折算手续费用的就是这个 `q`），消除口径撕裂。
3. `scripts/lp_netcover_inputs_v1_readonly.py:604-608` 的外部补丁**改为传参**，
   删掉那行手工换算——同一个换算不该存在两份。
4. 其余 5 个调用方**不要动**（`lp_portfolio_paper_runner`、`lp_swap_cost_model`、
   `strategy_pivot_d4_*`、`lp_tier_b_level2_replay` 三处）：
   它们的场景 quote 确实是 1，默认值使它们行为不变。
   **在报告里逐个确认这一点**（说明你检查过它们的 quote 确实是 1）。

## 验收标准

1. `quote=1.0` 时，`position_liquidity_raw` 的返回值与修改前**逐位相同**
   （用 `git show HEAD:scripts/lp_v3_fee_share.py` 加载旧版对照，
   跑至少 6 组参数，把两组数值贴进报告）。
2. `quote=0.99` 时返回 `207114224164452.517`（±1e-6 相对误差）——
   这是审计实测的正确值。
3. `shadow_runner` 用真实数据跑一次，`nav_start` 仍精确等于 `capital_usd`，
   `net_pnl` 与修改前**在 quote=1 的真实 pool_meta 下完全一致**
   （当前 pool_meta 没有 quote_usd_per_token1，默认走 1.0，所以结果不该变）。
   验证脚本：
   ```bash
   /root/lp-bot/.venv/bin/python - <<'PYEOF'
   import sys, sqlite3, json, tempfile, pathlib
   sys.path.insert(0,'/opt/lpbot/lp-bot-v3-origin-check')
   from decimal import Decimal
   from scripts.lp_rh_shadow_runner_v1_readonly import load_samples_from_db, run_episode, episode_summary
   from scripts.lp_rh_store_v1_readonly import open_store, migrate
   meta=json.load(open('reports/lp_rh/pool_meta.json'))
   src=sqlite3.connect('reports/lp_rh/scanner.db')
   samples,_=load_samples_from_db(src, pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca', limit=200)
   tmp=pathlib.Path(tempfile.mkdtemp()); conn=open_store(tmp/'t.db'); migrate(conn)
   steps=run_episode(conn, strategy_episode='v', samples=samples, position_usd=Decimal(1000),
                     horizon_hours=720.0, capital_usd=Decimal(10000), target_mode='SHADOW_SCENARIO',
                     now_fn=lambda:'2026-09-09T23:00:00Z', pool_meta=meta)
   s=episode_summary(steps); print('nav_start',s.get('nav_start'),'net_pnl',s.get('net_pnl'))
   PYEOF
   ```
   **注意**：采集器在持续写库，两次运行取到的样本不同，
   所以要在**同一次运行里**对比新旧实现，不要跨运行比数字。
4. `lp_netcover_inputs` 改动后，其既有测试全绿。
5. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4582 passed / 0 failed**，不得新增 failed。

## 不许动

`scripts/lp_rh_readiness_v1_readonly.py`、`scripts/lp_rh_coverage_audit_v1_readonly.py`、
`scripts/lp_bsc_*`、`scripts/lp_survival_*`、`scripts/strategy_pivot_d4_*`
（另一条线正在改这几个）、任何 `.db`、`reports/` 下任何文件。
既有测试**只允许新增测试**，但第 1、4 条验收若要求调整调用处参数，允许改那几行。

## 纪律

- **不要执行任何 git 命令**（`git show` 只读可用）。
- 不要重启 daemon，不要动 crontab。
- 单次写入 ≤ 150 行。
