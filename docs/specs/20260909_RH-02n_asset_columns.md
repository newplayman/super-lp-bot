# RH-02n：194 行有了，但六列是空的——字段名对不上，两列还被写死成 None

## 实测现状（主脑 2026-09-09 取证）

RH-02m 让 `rh_assets` 从 0 行变成 194 行。但抽样一行：

```
chain_id            = 4663
address             = 0xd95b44124e475743a7589e68f3d74008a5536d44
decimals            = 18
capability_json     = {"extended": "TRADABLE", "market": "TRADABLE", ...}
symbol_display      = None      <-- 读的是 asset_json["symbol"]，feed 发的是 tokenSymbol
uid                 = None      <-- 读的是 "uid"，feed 发的是 id
underlying          = None
multiplier_raw      = None      <-- write_assets 里写死 None
status              = None      <-- write_assets 里写死 None
source_payload_hash = None      <-- write_assets 里写死 None
```

**表填上了、列是空的**——与 `session` 被写死成 `"UNKNOWN"` 是同一形状。
`source_payload_hash` 尤其要命：这是**证据**表，没有 payload 哈希就无法证明来源。

## 实测字段映射（**直接用，不要再猜**）

| `rh_assets` 列 | REST 字段 | 实测值样例 | 类型 |
|---|---|---|---|
| `symbol_display` | `tokenSymbol` | `'CRM'` | str |
| `uid` | `id` | `'0x000…22015c295294037bfe416d3e45327b9'` | str |
| `underlying` | `isin` | `'US79466L3024'` | str |
| `status` | `status` | `'ASSET_STATUS_ACTIVE'`（194 条唯一取值） | str |
| `multiplier_raw` | `currentMultiplier` | **`'1.002210914971013375'`** | **str** |
| `decimals` | `tokenDecimals` | `18` | int（**已正确，不要动**） |
| `capability_json` | `tradingCapabilities` | 已正确 | （**不要动**） |

## ★精度硬约束★

`currentMultiplier` 是**十进制字符串、18 位小数、19 位有效数字**
（不是链上合约那个 1e18 定点整数——那是另一种格式，别混）。
`scripts/lp_rh_store_v1_readonly.py` 的 `_DECIMAL_TEXT_COLUMNS` 已把
`rh_assets.multiplier_raw` 列为 decimal TEXT。

**必须原样作为字符串写入，全程不得经过 `float`。**
`float('1.002210914971013375')` 会丢到 17 位有效数字，是静默精度损失。
若要校验数值，用 `decimal.Decimal`。

`pendingMultiplier` 实测是**空字符串 `''`**：空字符串一律转 `None`，
**不得把 `''` 存进库**（空串与"没有值"必须可区分）。

## 要改的两处（已用 `ast` 抽出，**不要再 grep**）

### A. `scripts/lp_rh_registry_v1_readonly.py` 的 `asset_from_json`
```
symbol_display=str(asset_json.get("symbol", "")),
uid=_opt_str(asset_json.get("uid")),
underlying=_opt_str(asset_json.get("underlying")),
```
改为**顶层原键优先、回退到实测键**（向后兼容，现有测试一条都不许红）：
`symbol` → 回退 `tokenSymbol`；`uid` → 回退 `id`；`underlying` → 回退 `isin`。
取不到时 `symbol_display` 保持 `""`、其余保持 `None`（与现状一致）。

### B. `scripts/lp_rh_evidence_writer_v1_readonly.py` 的 `write_assets`
```
"multiplier_raw": None,
"status": None,
"source_payload_hash": None,
```
改为：
- `multiplier_raw`：取 `currentMultiplier`，**原样字符串**，空串/缺失 → `None`。
- `status`：取 `status`，空串/缺失 → `None`。
- `source_payload_hash`：`sha256` of
  `json.dumps(asset_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
  的十六进制串。**同一 payload 必须得到同一 hash**（可复现）。

## 不许动
不改 `_extract_address` 与 `deployments` 回退（RH-02m 刚修好且已验证）。
不改 `decimals` / `capability_json` 的现有映射。不改 `write_attestations` /
`write_pool_registry`。不联网（测试全用构造数据）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_asset_columns_v1_readonly.py`（≤240 行，**≥16 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。**
把实测记录写成 fixture 常量 `REAL`（含上表全部字段，`deployments` 照 RH-02m 的形状）。必测：

- `asset_from_json(4663, REAL, …)` 的 `symbol_display == "CRM"`、
  `uid == REAL["id"]`、`underlying == "US79466L3024"`。
- 向后兼容：同时带顶层 `symbol`/`uid`/`underlying` 的旧 fixture，
  **取顶层那个**（构造成与实测键不同的值，各断言一次，共三条）。
- **★`write_assets` 后 `multiplier_raw` 读回**
  **完全等于 `'1.002210914971013375'` 这个字符串★**（逐字符相等，
  不是 `float` 近似；再断言 `Decimal(读回值) == Decimal(原值)`）。
- **★`multiplier_raw` 全程不经 float：断言读回值是 `str` 类型★**
- `currentMultiplier` 为 `''` → `multiplier_raw is None`（**不是 `''`**）。
- `currentMultiplier` 缺失 → `None`。
- `status` 写入为 `'ASSET_STATUS_ACTIVE'`；`status` 为 `''` → `None`。
- `source_payload_hash` 是 64 位十六进制串。
- **同一 payload 两次调用得到相同 hash**（可复现）。
- 不同 payload 得到不同 hash。
- 键顺序不同、内容相同的两个 dict 得到**相同** hash（`sort_keys=True` 的意义）。
- `write_assets` 写 3 条后 `written == 3`、`skipped == 0`、`skip_reasons == {}`。
- 六列在写入后**全部非 None**（用 `REAL` 构造，逐列断言）。
- `decimals` 仍为 18、`capability_json` 仍非空（证明没有回退破坏 RH-02m 的成果）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_asset_columns_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥16 全绿；全量 **0 failed / 14 skipped**（现有 4147 passed 一条都不许退）。
两条命令尾部原样贴出。
