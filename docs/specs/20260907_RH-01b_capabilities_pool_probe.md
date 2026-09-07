# RH-01b：RH 链能力矩阵与 V3/V4 池探针（离线可测；联网探针可选）

## 背景（一段）

PRD v1.1 §3.3、§7.2–7.4、§8.3、§19 RH-01，用例 T01、T06–T13。目标：为 Robinhood Chain（chainId 4663，Arbitrum 技术栈 L2，原生 gas ETH）建立"能力不是布尔值"的 venue 能力矩阵，以及 V3（factory+pool address）与 V4（PoolManager+PoolId/PoolKey）分开的池身份探针；任何未完成的核验都是 `DISCOVERED_NOT_ATTESTED`，不得升级为候选。`RpcPool`（`scripts/lp_rpc_pool_v1_readonly.py`）的 `CHAINS` 表没有 4663，本包**不改**该共享表，而是在 RH 模块内以参数注入端点列表（PRD §2.2："不复制失败探针"）。RH-01a 已提供 `scripts/lp_rh_registry_v1_readonly.py`（`AssetIdentity`、`SEED_ADDRESSES`、`RH_CHAIN_ID`），可 import。

## 新增文件（不改任何旧文件）

1. `scripts/lp_rh_capabilities_v1_readonly.py`（≤ 350 行，分次写）
   - `CAPABILITY_KEYS = ["discovery","state_read","history_read","fee_attribution","add_quote","remove_quote","swap_quote","simulate","unsigned_build","broadcast","reconcile"]`；状态枚举 `VERIFIED | UNVERIFIED | UNSUPPORTED | DEGRADED`。
   - `dataclass ProviderProbe`：`url, chain_id_hex, block_number, block_hash, client_version, supports_eth_call, supports_get_logs, supports_estimate_gas, error, fetched_at`。
   - `probe_provider(url, rpc=<callable(method, params)->result>) -> ProviderProbe`：依次 `eth_chainId`、`eth_blockNumber`、`eth_getBlockByNumber("latest", False)`（取 hash）、`web3_clientVersion`（失败可为 None）、`eth_call` 到 WETH `decimals()`（selector `0x313ce567`）、`eth_getLogs` 空范围（`fromBlock=toBlock=latest`, address=WETH）、`eth_estimateGas`（简单 value transfer 到自身，from=零地址允许失败→False）。`rpc` 可注入；默认实现用 `urllib.request`，**必须设 `User-Agent: curl/8.5.0`**（Cloudflare 对 Python-urllib 返回 403），超时 10s。JSON-RPC 响应若含 `error` 字段 → 记 `error`，不得当 0/空结果（T12）。
   - `chain_identity_gate(probe: ProviderProbe, expected_chain_id=4663) -> str`：`chain_id_hex` 解析后 == 4663 → `CHAIN_ID_OK`；46630/1/其它 → `CHAIN_ID_MISMATCH`（T01）；None → `CHAIN_ID_UNKNOWN`。
   - `provider_independence(probes: list[ProviderProbe]) -> dict`：同一 `client_version` 且 `block_hash` 完全同步且 URL host 相同或互为别名（简单规则：域名主体相同）→ `independent=False, reason="SAME_BACKEND_SUSPECTED"`；不同 host 且 block hash 在同高度一致或高度差 ≤ 2 → `independent=True`；同高度 hash 不一致 → `independent=None, reason="BLOCK_HASH_DIVERGENCE"`（T11、T13）。
   - `build_capability_matrix(probes, protocol_flags) -> dict`：对 venue `uniswap_v3@4663` 与 `uniswap_v4@4663` 输出每个 key 的状态：`discovery/state_read` 在 ≥1 provider `CHAIN_ID_OK` 且 `supports_eth_call` 时 `VERIFIED`，否则 `UNVERIFIED`；`history_read` 依 `supports_get_logs`；`simulate/unsigned_build/broadcast/reconcile` 一律 `UNVERIFIED`（本包不做）；`fee_attribution/add_quote/remove_quote/swap_quote` 一律 `UNVERIFIED`；V4 若 `protocol_flags["v4_state_view_address"]` 为空则 V4 全部 `UNSUPPORTED`。每项带 `evidence`（provider url + block_number）与 `expires_at`（fetched_at + 24h，ISO UTC）。
   - `main()`：`--rpc-url <url>` 可多次；`--offline-fixture <json>`（用固定响应回放，不联网）；`--out <RH_CAPABILITY_MATRIX.json>`。无 `--rpc-url` 且无 fixture → 输出全 `UNVERIFIED` 的矩阵并在 `notes` 写 `NO_PROVIDER_CONFIGURED`，退出码 0。环境变量 `RH_RPC_PRIMARY` / `RH_RPC_SECONDARY` 若存在则作为默认 url（只读取环境变量值，不打印到日志）。
2. `scripts/lp_rh_pool_probe_v1_readonly.py`（≤ 350 行，分次写）
   - `dataclass PoolIdentityV3`：`chain_id, factory, pool, token0, token1, fee, tick_spacing, code_nonempty:bool, factory_get_pool_matches:bool|None, attestation_status`。
   - `dataclass PoolIdentityV4`：`chain_id, pool_manager, pool_id, currency0, currency1, fee, tick_spacing, hooks, attestation_status`。
   - `dispatch_protocol(candidate: dict) -> str`：候选含 `pool_id`（32 字节 hex）且无 `pool` 地址 → `"v4"`；含 20 字节 `pool` 地址 → `"v3"`；都有或都无 → `"UNSUPPORTED_PROTOCOL"`（T08：V4 PoolId 绝不进入 V3 factory 探针）。
   - `probe_v3_pool(candidate, rpc, expected_chain_id=4663) -> PoolIdentityV3`：`eth_getCode(pool)` 非 `0x` 才继续；`eth_call` `token0()`/`token1()`/`fee()`/`tickSpacing()`（selectors `0x0dfe1681`、`0xd21220a7`、`0xddca3f43`、`0xd0c93a7c`）；再 `eth_call` factory `getPool(token0,token1,fee)`（selector `0x1698ee82`，参数 ABI 编码：两个 address 左补零到 32 字节 + uint24 fee 左补零）比对返回地址 == pool（T07：不匹配 → `attestation_status="IDENTITY_FAIL"`，且**不得**返回任何经济字段）。全部通过 → `"ATTESTED_SAME_BLOCK"` 并记录 `block_number/block_hash`；任何一步 JSON-RPC error/异常 → `"DISCOVERED_NOT_ATTESTED"` 且 `error` 字段保留原文（不得填 0）。
   - `probe_v4_pool(candidate, rpc, state_view=None) -> PoolIdentityV4`：本包只做身份解析（PoolKey → PoolId = keccak256(abi.encode(PoolKey)) 用纯 Python `hashlib.sha3_256`？**不行**，EVM keccak ≠ sha3-256；若仓库里已有 keccak 实现（`grep -rn keccak scripts/ | head`）则复用，否则 PoolId 计算标记 `UNVERIFIED_NO_KECCAK` 并保留输入 PoolKey）；`hooks != 0x0…0` → `attestation_status="UNSUPPORTED_HOOK_POLICY"`（T09）；不得对 PoolManager 调 `token0()`（T08）；不得把 PoolManager 余额当 TVL（T10：提供 `tvl_source` 字段，只允许 `"STATE_VIEW"` 或 `None`，任何调用方传入 `"POOL_MANAGER_BALANCE"` 抛 `ValueError`）。
   - `attestation_expired(record, current_impl_codehash) -> bool`：记录里的 `code_hash` 与当前 `eth_getCode` 的 keccak/或简单 sha256(code bytes) 不同 → True（T06：变化即过期，输出安全事件字段 `security_event="IMPLEMENTATION_CHANGED"`）。
   - `main()`：`--candidates <json>`、`--offline-fixture <json>`、`--rpc-url`、`--out <ASSET_ATTESTATIONS.json>`；与 RH-01a 的 `SEED_ADDRESSES` 联动：默认候选 = 种子池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`（V3）。
3. `tests/test_lp_rh_capabilities_v1_readonly.py`、`tests/test_lp_rh_pool_probe_v1_readonly.py`（各 ≤ 250 行）：用注入的假 `rpc` callable，**不联网**。覆盖 T01（46630 / 1 / 混入 4663 响应）、T06、T07、T08、T09、T10、T11、T12、T13、`NO_PROVIDER_CONFIGURED`、错误保留原文。每个断言具体值。fixtures 放 `tests/fixtures/rh/synthetic/`，标 `"data_kind": "SYNTHETIC_NOT_CHAIN_DATA"`。
4. `reports/rh_pivot/20260907T124500Z/RH-01b/RH_CAPABILITY_MATRIX.json` 与 `ASSET_ATTESTATIONS.json`：由 `main()` 用 `--offline-fixture` 生成一份（标 `synthetic=true`）；**若 worker 环境能联网**，再用 `--rpc-url https://rpc.mainnet.chain.robinhood.com` 生成一份真实版到同目录 `*_live.json`（失败则写 `RPC_PROBE_NOT_RUN.md` 记录错误原文，不伪造）。

## 不许动什么

- 不改任何现有 `scripts/*.py`（包括 `lp_rpc_pool_v1_readonly.py` 的 `CHAINS`）、`tests/*.py`、配置、六常量。
- 不 import web3 / eth_account / solders；不签名不广播；不读 `.env*`；不写 `reports/lp_rh/scanner.db`。
- 联网只允许对 `https://rpc.mainnet.chain.robinhood.com` 或 `RH_RPC_PRIMARY/SECONDARY` 做 JSON-RPC 只读方法（chainId/blockNumber/getBlock/call/getLogs/estimateGas/getCode/clientVersion）；总请求 ≤ 60 次。
- 单次 Write/Edit ≤150 行或 6000 字符；不整读 >300 行文件。

## 验收标准

- [ ] `git diff --stat` 只含 2 个新脚本、2 个新测试、fixtures、`reports/rh_pivot/20260907T124500Z/RH-01b/` 产物。
- [ ] 两个新测试文件全绿，合计 ≥ 16 个测试；全量 pytest = 上一基线 + 新增，0 failed，14 skipped。
- [ ] `dispatch_protocol({"pool_id": "0x"+"ab"*32})` 返回 `"v4"`；`probe_v3_pool` 在 factory 不匹配时 `attestation_status == "IDENTITY_FAIL"` 且结果无 `netcover`/`fee_ev` 键。
- [ ] `probe_provider` 对含 `{"error": {...}}` 的响应返回 `error` 非空、`block_number is None`。
- [ ] `grep -nE 'import (web3|eth_account|solders|solana)' scripts/lp_rh_capabilities_v1_readonly.py scripts/lp_rh_pool_probe_v1_readonly.py` 零命中。

## 验证命令（仓库根 `/opt/lpbot/lp-bot-v3-origin-check`）

```bash
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_capabilities_v1_readonly.py tests/test_lp_rh_pool_probe_v1_readonly.py -q -p no:cacheprovider 2>&1 | tail -3
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -2
/root/lp-bot/.venv/bin/python scripts/lp_rh_capabilities_v1_readonly.py --offline-fixture tests/fixtures/rh/synthetic/provider_probe_ok.json --out /tmp/cap.json && head -c 500 /tmp/cap.json
/root/lp-bot/.venv/bin/python scripts/lp_rh_pool_probe_v1_readonly.py --offline-fixture tests/fixtures/rh/synthetic/v3_pool_probe_ok.json --out /tmp/att.json && head -c 500 /tmp/att.json
git diff --stat; git status --short | grep -E 'lp_rh_(cap|pool)|fixtures/rh|RH-01b'
```
