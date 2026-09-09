# RH-02m：资产地址在 `deployments[]` 里，不在顶层——194 条全被静默跳过

## 实测证据（主脑 2026-09-09 用真实 REST 响应取证，不是推测）

```
collect_assets(_default_fetch)            -> 194 条记录，status=200
write_assets(...)  -> {"written": 0, "skipped": 194, "missing_fields": {}}
asset_from_json(4663, recs[0], "1", "x")  -> ValueError: ASSET_ADDRESS_INVALID
_asset_addresses(recs)                    -> []   （0 个地址）
```

`run_once` 的 `errors` 为 **空**，退出码 **0**。194 条真实资产一行没写，
**不抛异常、不报错、全量测试仍 4113 全绿**——静默假绿家族的又一实例。

**根因**：RH-02j 的测试用注入的假 `fetch_fn`，fixture 把地址放在顶层
`tokenAddress`；**真实响应把它放在 `deployments[]` 里**，需按 `chainId` 过滤。
容器键 `assets` 是对的（已 `--dry-run` 确认），错的是记录内部结构。

## 真实记录形状（实测，直接用）

```json
{"tokenSymbol": "CRM", "status": "ASSET_STATUS_ACTIVE", "tokenDecimals": 18,
 "isin": "...", "currentMultiplier": "...", "pendingMultiplier": "...",
 "tradingCapabilities": {...},
 "deployments": [{"contractAddress": "0xd95B44124e475743a7589e68F3D74008A5536D44",
                  "chainId": 4663, "networkName": "Robinhood Chain"}]}
```

顶层**没有** `tokenAddress` / `assetAddress` / `address` / `symbol` 任何一个。

## 要改的两个函数（已用 `ast` 抽出，**不要再 grep**）

### A. `scripts/lp_rh_registry_v1_readonly.py`
```
_ADDRESS_KEYS = (...)          # 现有顶层键元组，保留
def _extract_address(asset_json: Mapping[str, object]) -> Optional[str]:
    for key in _ADDRESS_KEYS:
        value = asset_json.get(key)
        if value is not None:
            return value
    return None
```
改为：顶层键**先查**（向后兼容，现有测试必须继续通过）；
顶层全空时**回退**到 `deployments[]`——取 `chainId == chain_id` 的第一条的
`contractAddress`。为此 `_extract_address` 增加**可选**参数
`chain_id: Optional[int] = None`；`asset_from_json` 调用时把它的 `chain_id` 传下去。
`deployments` 不是 list、元素不是 dict、无匹配 chainId → 返回 `None`（**不要猜**，
不要退而取第一条）。

### B. `scripts/lp_rh_evidence_collector_v1_readonly.py`
```
def _asset_addresses(asset_records) -> List[str]:   # 只查 tokenAddress/assetAddress/address
```
同样加 `deployments[]` 回退，同样按 `chainId` 过滤，同样去重保序、全部小写。
签名加**可选** `chain_id: Optional[int] = None`；`run_once` 调用处传 `chain_id`。

### C. 让静默跳过可见（纯增量，不得改动现有键）
`scripts/lp_rh_evidence_writer_v1_readonly.py` 的 `write_assets` 返回值
增加一个键 `skip_reasons: Dict[str, int]`，按 `ValueError` 的消息分组计数
（如 `{"ASSET_ADDRESS_INVALID": 194}`）。`written` / `skipped` /
`missing_fields` 三个现有键的语义与类型**保持不变**。

## 不许动
不改 `collect_assets` 的容器键逻辑（`assets` 已验证正确）。
不改 `write_pool_registry` / `write_attestations` 的签名。不联网（测试全用构造数据）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_asset_deployments_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。**
把上面那条真实记录形状写成 fixture 常量 `REAL_SHAPE`（一字不改地照抄）。必测：

- **★`asset_from_json(4663, REAL_SHAPE, "1", "s")` 成功，且 `address` 等于
  那个 `contractAddress` 的小写★**（这条直接复现并锁死本次缺陷）。
- **★`write_assets(conn, [REAL_SHAPE]*3, chain_id=4663, ...)` 的
  `written == 3` 且 `skipped == 0`★**（原为 0/194）。
- 向后兼容：顶层带 `tokenAddress` 的旧 fixture 仍成功，且**优先取顶层**
  （构造顶层与 deployments 不同的地址，断言取的是顶层那个）。
- `deployments` 里只有 `chainId != 4663` 的条目 → `ValueError
  ASSET_ADDRESS_INVALID`（**不得**退而取第一条）。
- `deployments` 为 `[]` / 缺失 / 不是 list / 元素不是 dict → 各断言一次抛
  `ASSET_ADDRESS_INVALID`（四条）。
- `deployments` 有多条、其中一条 chainId 匹配 → 取匹配那条，不取第一条。
- `contractAddress` 不是 40-hex → `ASSET_ADDRESS_INVALID`。
- `_asset_addresses([REAL_SHAPE], chain_id=4663)` 返回 1 个小写地址。
- `_asset_addresses` 对同一地址出现两次 → 去重后 1 个，且保序。
- `_asset_addresses(recs, chain_id=9999)` → `[]`（链不匹配不提取）。
- `write_assets` 的 `skip_reasons` 在全失败时为 `{"ASSET_ADDRESS_INVALID": N}`。
- `write_assets` 全成功时 `skip_reasons` 为空 dict（不是 None）。
- `write_assets` 的 `written`/`skipped`/`missing_fields` 三键仍存在且类型不变。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_asset_deployments_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**（现有 4113 passed 一条都不许退）。
两条命令尾部原样贴出。
