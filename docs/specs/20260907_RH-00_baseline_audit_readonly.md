# RH-00 只读基线与证据链审计 — Qwen 调研问题包（2026-09-07）

> 用途：主脑用 `qwen-code -p "<问题>" --disallowedTools Edit,Write` 逐题派发的**只读**调研问题。每题自包含，答案回给主脑，由主脑汇总成 `reports/rh_pivot/<UTC_RUN_ID>/RH-00/*`。
> 仓库：`/opt/lpbot/lp-bot-v3-origin-check`（HEAD `0e2b6e6`，分支 `feat/prd-v2.1-m0-shadow`）。数据库：`reports/lp_scanner/scanner.db`（已停写的迁移副本，可只读打开）。
> 上下文纪律：不整读 >300 行文件，用 `grep -n` / `sed -n 'a,bp'` 取片段；命令输出只贴尾部；不 cat 大 diff / db。
> 硬边界：只读；不改代码；不启动任何 daemon；不读 `.env*` / keystore。

## Q1 现有文件地图（→ P0_EXISTING_CODE_MAP.md）

对下列文件逐个给出：路径是否存在、行数、公开函数/类名与行号（`grep -nE '^(def|class) '`）、被哪些其他 `scripts/*.py` 或 `tests/*.py` import（`grep -rln`）：
`scripts/lp_rpc_pool_v1_readonly.py`、`scripts/lp_universe_screener_v1_readonly.py`、`scripts/lp_netcover_inputs_v1_readonly.py`、`scripts/lp_netcover_engine_v1_readonly.py`、`scripts/lp_swap_cost_model_v1_readonly.py`、`scripts/lp_scanner_daemon_v1_readonly.py`、`scripts/lp_shadow_gate_v1_readonly.py`、`scripts/lp_funnel_autopsy_v1_readonly.py`、`scripts/lp_stock_token_universe_v1_readonly.py`、`scripts/lp_stock_tier_policy_v1_readonly.py`、`scripts/lp_stock_tier_acceptance_v1_readonly.py`、`scripts/lp_panel_server_v1_readonly.py`、`execution/base_m1_executor_v1.py`。
另列 `scripts/` 下 `lp_*_readonly.py` 总数、`tests/test_*.py` 总数。输出 Markdown 表。

## Q2 六常量按名核对

在整个 `scripts/` 与 `execution/` 中 grep 这六个名字，给出每处定义的文件:行号:值：`STABLE_MIN_FRAC`、`NETCOVER_SHADOW`、`NETCOVER_TINY_LIVE`、`POSITION_TVL_SHARE`、`HARD_POSITION_TVL_SHARE`、`LVR_COEFFICIENT_MODEL`。若有同名不同值或在别的文件里被重新赋值，单独列出。预期：0.7 / 1.0 / 1.5 / 0.0005 / 0.001 / 0.50。

## Q3 终闸字段生产者映射（→ FIELD_PRODUCER_MAP.md）

以 `scripts/lp_scanner_daemon_v1_readonly.py` 的 `_enforce_fifth_gate`（约 :1242）为终闸入口，列出该合取式用到的每一个布尔/字段（如 `prior_vetted`、`netcover_pass`、`permanent_reason`、`position_cap_pass`、`entry_eligible`），对每个字段回答：① 在哪个文件哪个函数被**赋值/写入**（生产者）；② 写进 `scanner.db` 哪张表哪一列（用 `grep -n 'INSERT\|UPDATE\|CREATE TABLE'`）；③ 谁读取；④ 哪个测试断言它。若找不到生产者或恒为 None，明确写 `NO_WRITER`。另外核对 `market_sessions`、`rpc_severe_incidents` 两张表：`CREATE TABLE` 在哪，`INSERT` 在哪（预期 0 处），`SELECT` 在哪。

## Q4 factory_registry_probe_incomplete 追根（→ LEGACY_FAILURE_AUTOPSY.json 素材）

① `grep -rn factory_registry_probe_incomplete scripts/` 列出所有出现处，说明每处触发条件（贴该处前后 15 行）。② 只读打开 `reports/lp_scanner/scanner.db`（`sqlite3.connect('file:...?mode=ro', uri=True)`），在 `opportunity_scores` 表找最新一个批次（按批次/时间列），统计该批次里 reason 含 `factory_registry_probe_incomplete` 的行数/总行数，并列出这些池的 pool 标识、chain、project 前 10 个。③ 同一批次里挑 2 个**没有**该原因且 `netcover` 有数值的池作为阳性对照，贴它们的关键字段（pool、project、fee tier、tvl、netcover、vetted）。④ 从代码判断这个 reason 是由哪个 RPC 方法/哪个探针函数失败导致（给函数名与行号）。不要下"经济上不可行"的结论。

## Q5 A/B 档 existing_terminal_conjunction 缺口核实

`grep -rn existing_terminal_conjunction scripts/ tests/`：谁读（预期 `lp_stock_tier_acceptance_v1_readonly.py` 约 :79）、谁写（预期无）。给出证据行。

## Q6 只读脚本是否 import 签名/广播能力

对 `scripts/lp_*_readonly.py` 全部文件 `grep -lE 'import (web3|eth_account|solders|solana)|sign_transaction|send_raw_transaction|sendTransaction|private_key|keystore'`，列出命中文件与行；预期只在 `execution/` 内出现。

## Q7 测试假绿点位复核

核对 B1 §10.8 三处：`tests/test_lp_base_probe_dry_run_builder_v1_readonly.py:264` 函数体是否只有 `pass`；`tests/test_lp_panel_server_v1_readonly.py:231`、`tests/test_lp_netcover_inputs_v1_readonly.py:777` 的断言内容。贴各 10 行上下文，不改。
