# 证据表为什么仍是 0 行：不是没上线，是上线了也写不进

日期：2026-09-09 主脑实测（真实 REST 响应，非推测）

## 交接的判断需要修正

`HANDOFF_20260909_CN.md` §6 说 RH-02j「只是能力就绪，尚未上线」，
下一任只需在「加 cron / 并入现有守护 / 手工按需跑」三者中选一个。

**实测表明选哪个都没用**：手工跑一次 `--once` 后两张表**仍是 0 行**。

## 证据链

```
$ python scripts/lp_rh_evidence_collector_v1_readonly.py --db reports/lp_rh/scanner.db --dry-run
dry-run: status=200
dry-run: record keys: ['currentMultiplier','deployments','id','isin','logoUrl',
                       'pendingMultiplier','status','tokenDecimals','tokenName',
                       'tokenSymbol','tradingCapabilities']

$ ... --once            # 退出码 0，report["errors"] == []
rh_assets                    0 行     （跑之前也是 0 行）
rh_contract_attestations     0 行
```

直接调内部函数定位断点：

```
collect_assets(_default_fetch)             -> 194 条记录，status=200
write_assets(conn, recs, chain_id=4663…)   -> {"written": 0, "skipped": 194,
                                               "missing_fields": {}}
asset_from_json(4663, recs[0], "1", "x")   -> ValueError: ASSET_ADDRESS_INVALID
_asset_addresses(recs)                     -> []      (0 个地址)
```

## 根因

`_extract_address`（`lp_rh_registry_v1_readonly.py`）与 `_asset_addresses`
（`lp_rh_evidence_collector_v1_readonly.py`）都只查**顶层**键
`tokenAddress` / `assetAddress` / `address`。真实记录顶层**没有任何地址字段**，
地址在：

```json
"deployments": [{"contractAddress": "0xd95B44124e475743a7589e68F3D74008A5536D44",
                 "chainId": 4663, "networkName": "Robinhood Chain"}]
```

`write_assets` 对 `ValueError` 的处理是 `skipped += 1; continue`——
**194 条全部静默跳过，不抛异常、不进 `errors`、退出码 0。**

## 为什么 14 个自带测试全绿

RH-02j 的测试用注入的假 `fetch_fn`，fixture 把地址放在顶层 `tokenAddress`。
**测试的 fixture 与真实契约脱钩**，于是代码在假数据上永远正确、在真实数据上永远为空。

这是静默假绿家族第 9 例（「假 `call_fn` 不看方法名，错名字能通过全部 mock 测试、
在每一次真实调用上失败」）**在数据结构层面的同构体**。

交接提醒了「`/rhj/assets` 的容器键建议先 `--dry-run` 确认」——方向是对的但对象错了：
**容器键 `assets` 恰恰是正确的**，错的是记录内部结构。

## 处置

`docs/specs/20260909_RH-02m_asset_address_from_deployments.md` 已派工：
顶层键优先（向后兼容），回退到 `deployments[]` 并按 `chainId` 过滤；
`write_assets` 增加 `skip_reasons` 计数键，让「194 条全跳过」不再无声。

## 留给流程的一条

**「能力就绪」不等于「已上线」，「已上线」也不等于「写得进」。**
验收填表类模块，必须实跑一次真实输入并对比 `COUNT(*)`——
本例的 14 个自带测试、`--dry-run` 的 200、退出码 0，三样都不能替代数行数。
