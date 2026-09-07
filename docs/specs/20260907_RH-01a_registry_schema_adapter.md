# RH-01a：RH 资产注册表与 assets 新旧 schema 适配器（只读、离线可测）

## 背景（一段）

PRD v1.1（`docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md` §7.1、§9.1、§19 RH-01、用例 T02–T05）要求：资产主键为 `(chain_id, token_address)`，symbol 只作显示；Robinhood 官方 `/rhj/assets` 存在两种结构——文档示例的 `LEGACY_FIELDS`（`tradingCapabilities.fractionalTradability` / `allDayTradability` / `extendedHoursFractionalTradability`）和实际观察到的 `SESSION_NESTED`（`tradingCapabilities.market|extended|overnight.{whole,fractional} = "TRADING_STATUS_TRADABLE"`，另有 `tokenDecimals`）。实现必须双适配、未知→UNKNOWN、矛盾→`SCHEMA_SEMANTIC_CONFLICT`，任何未知/缺失/null/空串都不等于"可交易"。本包不联网也能全绿；联网抓取真实响应是可选步骤。

## 新增文件（不改任何旧文件）

1. `scripts/lp_rh_registry_v1_readonly.py`（目标 ≤ 350 行，分多次 Write/Edit，每次 ≤150 行）
   - 常量：`RH_CHAIN_ID = 4663`、`RH_TESTNET_CHAIN_ID = 46630`；种子地址表 `SEED_ADDRESSES`（只作发现种子，字段 `attested=False`）：WETH `0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73`、USDG `0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168`、V3 factory `0x1f7d7550b1b028f7571e69a784071f0205fd2efa`、V3 position manager `0x73991a25c818bf1f1128deaab1492d45638de0d3`、候选池 USDG/WETH `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`。
   - `dataclass AssetIdentity`：`chain_id:int, address:str(小写校验和无关，统一 lower)、symbol_display:str, issuer:str|None, uid:str|None, underlying:str|None, decimals:int|None, metadata_version:str, source:str, attested:bool=False`。
   - `dataclass SessionCapability`：`market:str, extended:str, overnight:str`，每项取值只能是 `TRADABLE | NOT_TRADABLE | UNKNOWN`；再加 `schema_kind: "LEGACY_FIELDS"|"SESSION_NESTED"|"UNKNOWN"|"SCHEMA_SEMANTIC_CONFLICT"`，`raw_flags: dict`。
   - `detect_schema(asset_json) -> str`：仅有 legacy 三键→`LEGACY_FIELDS`；仅有 `market/extended/overnight` 嵌套→`SESSION_NESTED`；两者都有→逐项比较语义，一致则 `SESSION_NESTED`（记录 `both_present=True`），不一致→`SCHEMA_SEMANTIC_CONFLICT`；都没有→`UNKNOWN`。
   - `normalize_capability(asset_json) -> SessionCapability`：LEGACY 映射规则：`fractionalTradability` 为 bool True→market=TRADABLE，False→NOT_TRADABLE，其它→UNKNOWN；`extendedHoursFractionalTradability`→extended；`allDayTradability`→overnight。SESSION_NESTED：字符串严格等于 `TRADING_STATUS_TRADABLE`→TRADABLE，等于 `TRADING_STATUS_NOT_TRADABLE`/`TRADING_STATUS_CLOSING_ONLY`→NOT_TRADABLE（closing-only 必须落 NOT_TRADABLE 且在 `raw_flags` 保留原串），其它字符串/None/缺失→UNKNOWN。`whole` 与 `fractional` 不一致时取更保守者（NOT_TRADABLE > UNKNOWN > TRADABLE）。CONFLICT/UNKNOWN schema 时三项全 UNKNOWN。
   - `asset_from_json(chain_id, asset_json, metadata_version, source) -> AssetIdentity`：地址缺失或非 40 hex 抛 `ValueError("ASSET_ADDRESS_INVALID")`；`tokenDecimals` 缺失→`decimals=None`。
   - `verify_identity(candidate: AssetIdentity, registry: Mapping[str, AssetIdentity]) -> str`：registry 以 lower address 为键；地址不在 registry→`ASSET_IDENTITY_MISMATCH`；地址在但 symbol 不同→`ASSET_IDENTITY_MISMATCH`（symbol 只是显示，但 registry 与候选自称不一致要报）；uid/decimals 不一致→`ASSET_IDENTITY_MISMATCH`；一致→`ASSET_IDENTITY_OK`。**symbol 相同地址不同永远 MISMATCH**（T02）。
   - `is_new_position_allowed(cap: SessionCapability, session: str) -> bool`：只有对应 session 为 `TRADABLE` 才 True；UNKNOWN/CONFLICT 一律 False（T05）。
   - `load_assets(path) -> list[dict]`：从本地 JSON 文件读（不联网）；`main()` 支持 `--assets-json <file> --registry-out <file>`，输出 `ASSET_ATTESTATIONS.json` 雏形（每资产 `attested=False`，`attestation_status="DISCOVERED_NOT_ATTESTED"`）。
   - 模块顶部 docstring 写明：只读、不 import 任何签名/广播库、不联网（联网抓取在 RH-01b 的 probe 里做）。
2. `tests/test_lp_rh_registry_v1_readonly.py`（≤ 250 行）：
   - fixture 目录 `tests/fixtures/rh/synthetic/assets_legacy.json`、`assets_session_nested.json`、`assets_conflict.json`、`assets_unknown_enum.json`（自己构造，文件顶部或 JSON 里标 `"data_kind": "SYNTHETIC_NOT_CHAIN_DATA"`）。
   - 至少覆盖：T02（symbol 相同地址不同→MISMATCH）、T03（legacy 映射；null/空/closing-only 不变 TRADABLE）、T04（nested：market/extended/overnight 区分正确）、T05（未知 enum→UNKNOWN 且 `is_new_position_allowed` False；两 schema 矛盾→`SCHEMA_SEMANTIC_CONFLICT`）、地址非法→ValueError、`whole`/`fractional` 不一致取保守、`decimals` 缺失→None、chain_id 46630 的资产 `verify_identity` 对 4663 registry→MISMATCH（T01 的资产侧）。每个测试断言具体值，不得只 `is not None`。
3. `reports/rh_pivot/20260907T124500Z/RH-01a/SCHEMA_COMPATIBILITY.md`（≤ 80 行）：两种 schema 的字段对照表、映射规则、CONFLICT 定义、closing-only 处理、已知未覆盖情况。

## 不许动什么

- 不改任何现有 `scripts/*.py`、`tests/*.py`、配置、六常量；不动 `.gitignore`；不动未提交的 `lp_rpc_pool_v1_readonly.py` 改动。
- 不联网、不 curl、不读 `.env*`、不 import web3/eth_account/requests 之外的网络库（本包根本不需要 requests）。
- 不写 `reports/lp_rh/scanner.db`（那是 RH-02）。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件（参考现有风格可 `sed -n '1,80p' scripts/lp_stock_token_universe_v1_readonly.py`）。

## 验收标准

- [ ] `git diff --stat` 只含上述 3 类新文件（1 脚本、1 测试、fixtures、1 md）。
- [ ] `pytest tests/test_lp_rh_registry_v1_readonly.py -q` 全绿，测试数 ≥ 10。
- [ ] 全量 `pytest tests/ -q -p no:cacheprovider`：passed = 上一基线（RH-00b 后为 3111）+ 新增数，0 failed，14 skipped。
- [ ] `grep -nE 'import (web3|eth_account|solders|solana|requests)|sign|broadcast|private_key|keystore' scripts/lp_rh_registry_v1_readonly.py` 零命中（docstring 里的"不 import"说明除外）。
- [ ] `python scripts/lp_rh_registry_v1_readonly.py --assets-json tests/fixtures/rh/synthetic/assets_session_nested.json --registry-out /tmp/rh_reg.json` 退出码 0，输出里每项 `attestation_status == "DISCOVERED_NOT_ATTESTED"`。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_registry_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
/root/lp-bot/.venv/bin/python scripts/lp_rh_registry_v1_readonly.py --assets-json tests/fixtures/rh/synthetic/assets_session_nested.json --registry-out /tmp/rh_reg.json && head -c 600 /tmp/rh_reg.json
grep -nE 'import (web3|eth_account|solders|solana|requests)' scripts/lp_rh_registry_v1_readonly.py || echo NO_NETWORK_OR_WALLET_IMPORTS
git diff --stat; git status --short | grep -E 'lp_rh|fixtures/rh|RH-01a'
```
