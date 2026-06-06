# Stage A: 输入证据审计

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COLLECTOR_FIX_V1`
- audit_stage: `A_INPUT_EVIDENCE_AUDIT`
- audited_at_utc: `2026-06-06T08:05:00Z`

## 0. 目的

锁定 12h 阶段"声明 universe vs 实际采集" gap 的根因, 明确本轮 fix 范围 + 不动作.

## 1. 5 个核心输入证据

| 标签 | 路径 | 关键事实 |
|---|---|---|
| `real_pool_universe_for_12h` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` | selected_real_pool_count=**33**, placeholder_pool_count=**0**, real_pool_universe_used=true, all_pools_are_real_on_chain=true (8 orca clmm + 5 orca stable + 10 raydium_clmm + 10 raydium_cpmm) |
| `12h_node_report` | `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` | gate=**PASS**, full_sample=true, coverage_scope=**partial_solana_real_pool_universe**, do_not_treat_as_full_coverage=**true**, **all_pools_are_smoke_placeholder=true**, pool_coverage_count=60, quote/fee/ev ready=0 |
| `12h_corrected_verdict` | `reports/lp_long_horizon_readonly_12h_extension/20260605_082120/CORRECTED_FINAL_VERDICT.json` | gate=PASS (15/15), 12/12 ckpts, runtime=720, source_supervisor_finalize_failed=true (post-12h block NameError) |
| `collector_v1` | `scripts/lp_long_horizon_readonly_collector_v1.py` (22277 B) | modes: design + smoke; 缺 `--pool-universe` / `--max-pools` / `--max-snapshots` / `--run-id` CLI args; 当前 smoke 跑 5 placeholder |
| `stage_runner` | `scripts/run_lp_long_horizon_readonly_stage_once.sh` (522 行) | 当前传给 collector: `--mode smoke --pools-per-protocol 5 --out ${CKPT_DIR} --no-wallet --no-tx --no-bridge --dry-run`. **没有** 把 POOL_UNIVERSE_PATH 传给 collector |

## 2. 关键断言

| 断言 | 值 |
|---|---|
| `real_pool_universe_exists` | ✅ **true** |
| `real_pool_universe_path` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` |
| `selected_real_pool_count` | **`33`** |
| `placeholder_pool_count_in_request_config` | **`0`** (Stage C universe 是干净的) |
| `12h_actual_collection_used_placeholder` | ✅ **true** (collector 没接通 real universe, 仍跑 smoke placeholder) |
| `all_pools_are_smoke_placeholder_in_12h` | ✅ **true** (5 unique placeholder `<smoke_pool_*_a>`) |
| `pool_coverage_count_in_12h` | `60` (5 placeholder × 12 ckpts) |
| `unique_pool_count_in_12h` | `5` (5 placeholder, **不**是 33 real pools) |
| `quote_ready_pool_count_in_12h` | **`0`** |
| `fee_ready_pool_count_in_12h` | **`0`** |
| `ev_ready_pool_count_in_12h` | **`0`** |
| `data_insufficient_count_in_12h` | `60` |
| `cannot_advance_to_24h` | ✅ **true** (real universe 没有被 collector 使用) |
| `do_not_treat_as_full_coverage` | ✅ **true** |
| `12h_node_report_status` | **PASS (corrected; not a full-universe verdict)** |
| `12h_corrected_gate_pass` | ✅ **true** (15/15 gate checks pass) |
| `12h_actual_runtime_minutes` | `720` |
| `12h_supervisor_self_status` | **FAIL** (post-12h block NameError on bash `${REAL_GATE_PASS}`) |

## 3. 根因分析 (primary + secondary)

### 3.1 Primary bug: collector 选了真实池清单, 实际仍采 placeholder

- `scripts/lp_long_horizon_readonly_collector_v1.py` 不接受 `--pool-universe` CLI arg
- 即便 stage runner `real_pool_universe_for_12h.json` preflight hard guard 验证了 universe 是真实的 (real_pool_universe_used=true, all_pools_are_real_on_chain=true, placeholder_pool_count=0), 实际 collector 仍 hardcoded 跑 smoke placeholder
- Stage runner 当前传给 collector: `--mode smoke --pools-per-protocol 5 --out ${CKPT_DIR} --no-wallet --no-tx --no-bridge --dry-run` (没有 `--pool-universe`)
- 上游 collector 内部 hardcoded `protocol_count=5, pool_per_protocol=5` (per `smoke_mode()` in collector), 输出 5 个 `<smoke_pool_*_a>` placeholder
- 12h actual data = 60 placeholder rows, 0 real on-chain data

### 3.2 Secondary bug (V3 supervisor finalize line 435 + 493)

- `scripts/run_lp_long_horizon_readonly_stage_once.sh` Stage 4 (post-12h FINAL_VERDICT 写) + V3 fix (CORRECTED_FINAL_VERDICT_FALLBACK.json) **两个 python heredoc 都用了 bash `${REAL_GATE_PASS}` 变量在 Python ternary 中**:
  ```python
  "recommended_next_stage": "X" if ${REAL_GATE_PASS} else "Y"
  ```
- bash interpolation 把 `${REAL_GATE_PASS}` 替换为 lowercase `true` (or `false`), Python 看到 `if true else` 触发 `NameError`
- 两次都 crash, fail-safe trap 写 default-zeros FAIL verdict
- 修复路径 (下一轮 LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT): 改用 `<<'PYEOF'` quoted heredoc, 或 `${REAL_GATE_PASS^^}` 大写, 或在 Python 端用 `agg["actual_runtime_valid_for_12h_gate"]`

## 4. 改进路径 (本轮)

| Stage | 内容 |
|---|---|
| B | collector v1 新增 `--pool-universe` / `--max-pools` / `--max-snapshots` / `--run-id` CLI args; 接通 real pool universe JSON, 拒绝 placeholder, 写真实池 snapshots |
| C | stage runner 转发 `--pool-universe` 给 collector; 缺时 FAIL, 不得默默回退 placeholder |
| D | 短 smoke: 5 真实池 × 1 snapshot, 验证 collector 不再跑 placeholder |
| E | pytest 8+ 项 + go test + forbidden process check |
| F | FINAL_VERDICT (含 spec-required 完整字段, 5-stage allowed next stages only) |
| G | git add + commit + push |

## 5. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d
- ❌ 不启动长期 collector (本轮只短 smoke: 5 池 × 1 snapshot)
- ❌ 不启动新 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 V2 12h FINAL_VERDICT (FAIL verdict 保留)
- ❌ **不**修改 V2 6h FINAL_VERDICT + V2 6h corrected verdict
- ❌ **不**修复 V3 supervisor finalize bug (本轮 read-only, 修复留给下一轮 LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT)
- ❌ can_run_probe_now (locked false)
- ❌ tiny_canary_allowed (locked "no")
- ❌ edge_proven (locked "no")

## 6. 一致性结论

- 4 个核心输入证据全部存在 ✅
- 根因锁定: collector 不接受 `--pool-universe` CLI arg, 即便 stage runner 验证了 universe ✅
- 改进路径清晰: 修 collector CLI + stage runner 转发 + 短 smoke 验证 ✅
- 锁定字段全部保持 ✅
- LP strategy research 仍处于 freeze ✅

**Stage A PASS** → 进入 Stage B (collector CLI 修复).
