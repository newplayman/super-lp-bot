# RH-02t：一次瞬时 RPC 失败让资产被静默跳过，只留下一个数字

## 实测证据（主脑 2026-09-09）

填充后 `rh_assets` 194 行，`rh_contract_attestations` 只有 193 行，
报告里唯一的线索是 `"collect_skipped": 1`。

追出来缺的是 `0x348be1a8663f15edde5cdf8a96bb69078f7ab6fd`（WULF / TeraWulf）。
它**不该被跳过**——直查 `rpc.ordofi.network`：

```
CRM  eth_getCode -> 0x6080604052600a600c565b...  283 字节
WULF eth_getCode -> 0x6080604052600a600c565b...  283 字节   （同一 beacon proxy）
```

链上有代码、`status` 是 `ASSET_STATUS_ACTIVE`、`chainId` 4663，一切正常。
唯一的解释是采集那一刻 `eth_getCode` 对它的调用瞬时失败了。

## 根因：错误被 `continue` 吞掉

`scripts/lp_rh_evidence_collector_v1_readonly.py` 的 `collect_attestations`：
```
code, err = _call(rpc_fn, "eth_getCode", [address, "latest"])
if err or not isinstance(code, str) or code in ("0x", ""):
    continue          # <== err 在这里被丢弃，不进 errors，不留原因
```
外部只能看到 `run_once` 里算出来的
`report["attestations"]["collect_skipped"] = len(addresses) - len(records)`。

**「链上真的没有合约」与「网络抖了一下」被压成同一个数字 1。**
前者是关于这条链的事实，后者是采集器的瞬时故障——两者必须可区分。

`_block_hash` 失败时 `return []` 同理：全部地址被跳过，原因同样不落地。

## 只改一个文件 + 其测试（纯增量，不得改变既有跳过行为）

### `scripts/lp_rh_evidence_collector_v1_readonly.py`

- `collect_attestations(rpc_fn, addresses, *, beacon, skip_out=None)`
  **新增可选参数 `skip_out`**（`dict` 或 `None`）。签名其余部分与返回值
  **保持不变**（现有调用方与测试不得受影响）。
  给出 `skip_out` 时，往里写 `{address: reason}`，`reason` 取值：
  - `"RPC_ERROR:<err 文本，截断 80 字符>"` —— `_call` 返回了 err
  - `"NO_CODE"` —— 返回 `"0x"` 或空串（链上确实没有合约）
  - `"CODE_NOT_STRING"` —— 返回值类型不对
  - `_block_hash` 失败时，**每个地址**都写
    `"BLOCK_HASH_UNAVAILABLE:<err 文本，截断 80 字符>"`
  **跳过与否的判定逻辑一个字都不许改**，只增加记录。
- `run_once`：调用处传入一个新 dict，并把结果放进
  `report["attestations"]["skip_reasons"]`。
  `collect_skipped` 这个既有键**保留不动**（语义与类型不变）。

## 不许动
不改 `_call` / `_block_hash` / `_beacon_implementation` 的签名与判定逻辑。
不改 `collect_assets`、不改任何 writer、不改表结构。不联网（测试用假 `rpc_fn`）。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 新增测试 `tests/test_lp_rh_attestation_skips_v1_readonly.py`（≤240 行，**≥14 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：

- **★`eth_getCode` 返回 err → `skip_out[addr]` 以 `"RPC_ERROR:"` 开头，
  且该地址不在返回的 records 里★**（复现 WULF 这次的情形）
- **★`eth_getCode` 返回 `"0x"` → `skip_out[addr] == "NO_CODE"`★**
  （与上一条必须是不同的值——这正是本包的全部意义）
- 返回非字符串 → `"CODE_NOT_STRING"`。
- `_block_hash` 失败 → 传入的三个地址**每个**都在 `skip_out` 里，
  值以 `"BLOCK_HASH_UNAVAILABLE:"` 开头，且返回 `[]`。
- 正常地址不出现在 `skip_out` 里。
- 三个地址中间那个失败 → 另两个仍正常返回（失败不中断其余）。
- err 文本超长时被截断到 80 字符以内。
- **不传 `skip_out` 时行为与从前完全一致**：返回值相同、不抛异常（两条断言）。
- `skip_out` 传入已有内容的 dict 时，原有键**不被清空**（只增不删）。
- `run_once` 的报告里出现 `attestations.skip_reasons`。
- `run_once` 的 `collect_skipped` **仍然存在且为整数**（既有键不破坏）。
- `collect_skipped` 的数值与 `len(skip_reasons)` 一致。
- 全部地址都正常时 `skip_reasons == {}`（空 dict，不是 None）。
- 返回的 records 内容与不传 `skip_out` 时逐字段相同（证明只是旁路记录）。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_attestation_skips_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 **0 failed / 14 skipped**（现有 4197 passed 一条都不许退）。
两条命令尾部原样贴出。
