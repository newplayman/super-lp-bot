# RH-02h：把身份与能力证据落库（Stage A 的硬阻塞）

## 背景

`STAGE_A_BLOCKERS_BEYOND_COVERAGE_20260909.md` 实测：
**五张证据表全空**，采集器源码里一次都没提到它们，没有任何脚本 insert。

PRD §21.1 要求 Stage A「**身份和能力证据清楚**」。
**即使覆盖率在第 90 小时跨过 99%，没有这些证据 Stage A 仍然毕不了业。**

产出证据的三个模块（`lp_rh_registry` / `lp_rh_capabilities` / `lp_rh_pool_probe`）
**都已存在且有测试，缺的只是把它们的输出写进库**。本包只做这一件事。

## 本包只做写入，不改任何产出逻辑

**不要修改那三个模块。** 只调用它们，把返回值映射进表。
若某个字段模块不产出，**写 `NULL` 并在报告里列出**，不要编造。

## 目标表结构（已抽好，照此映射，不要自己去查）

```
rh_assets                主键 (chain_id, address, metadata_version)
  必填: chain_id INTEGER, address TEXT, metadata_version INTEGER, updated_at TEXT
  可空: symbol_display, uid, underlying, decimals, multiplier_raw, status,
        capability_json, source_payload_hash

rh_pool_registry         主键 (chain_id, protocol, pool_key)
  必填: chain_id, protocol, pool_key, attestation_status TEXT, discovered_at TEXT
  可空: pool_address, pool_id, token0, token1, fee, tick_spacing, hooks

rh_contract_attestations 主键 (chain_id, address, block_hash, policy_version)
  必填: chain_id, address, block_hash, policy_version, attestation_status, created_at
  可空: code_hash, implementation, abi_version, evidence_json, expires_at
```

## 三个模块的接口（已抽好）

```
lp_rh_registry:     asset_from_json(chain_id, asset_json, metadata_version, source)
                    normalize_capability(asset_json)   detect_schema(asset_json)
                    verify_identity(candidate, registry)   load_assets(path)
lp_rh_capabilities: probe_provider(url, rpc, weth_address, fetched_at)
                    chain_identity_gate(probe, expected_chain_id)
                    build_capability_matrix(probes, protocol_flags)
lp_rh_pool_probe:   dispatch_protocol(candidate)   probe_v3_pool(candidate, rpc, expected)
                    attestation_expired(record, current_impl_codehash)
```

需确认返回字段时只 `grep -n "return {" <单个文件>` 局部看，**不要通读**。

## 只写一个文件 + 其测试

1. `scripts/lp_rh_evidence_writer_v1_readonly.py`（≤300 行）
   - `write_assets(conn, assets_json, *, chain_id, metadata_version, source)`
     对每个资产调 `asset_from_json` + `normalize_capability`，写 `rh_assets`。
     `capability_json` 存归一化后的能力 JSON。
   - `write_pool_registry(conn, candidates, *, chain_id)`
     对每个池调 `dispatch_protocol` 决定 protocol，写 `rh_pool_registry`。
     `attestation_status` 未经证实时写 `"DISCOVERED_NOT_ATTESTED"`，
     **不得默认写成已证实**。
   - `write_attestations(conn, probes, *, chain_id, policy_version)`
     写 `rh_contract_attestations`。
   - 全部使用 `INSERT OR REPLACE`（主键已定义，幂等）。
   - 每个函数返回 `{"written": int, "skipped": int, "missing_fields": {列名: 次数}}`——
     **`missing_fields` 让缺哪些字段可见，而不是静默写 NULL。**
   - `main()`：`--db --assets-json --candidates-json --probes-json --out`，
     **纯离线**（数据由 JSON 文件喂入，本模块不联网）。

2. `tests/test_lp_rh_evidence_writer_v1_readonly.py`（≤260 行，**≥14 测试**）
   顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。
   **内存 SQLite（`migrate()` 建表），不许联网、不许写 `reports/`。** 必测：
   - 写入后 `rh_assets` 行数正确，主键三元组正确。
   - 同一资产写两次只有一行（`INSERT OR REPLACE` 幂等）。
   - 模块不产出的字段写 `NULL`，且计入 `missing_fields`（**断言该字典非空**）。
   - `attestation_status` 在未经证实时是 `"DISCOVERED_NOT_ATTESTED"`
     （**自证其罪：断言它不是任何表示「已证实」的值**）。
   - `rh_pool_registry` 的 `protocol` 由 `dispatch_protocol` 决定，不是硬编码。
   - 必填列缺失时**抛出并指明列名**，不要写空字符串蒙混。
   - 三个 write 函数各自的 `written`/`skipped` 计数正确。
   - 空输入 → `written == 0`，不抛异常。
   - `chain_id` 不是 4663 的资产被 `skipped`（**身份闸不能在写入层被绕过**）。
   - 写入不修改任何其他表（前后逐表 COUNT 比对）。

## 不许动
不改那三个模块。不写 `reports/lp_rh/` 下的活库（测试用内存库）。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。
**先落盘骨架再逐个填充**，不要攒到最后一次性写。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_evidence_writer_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥14 全绿；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
