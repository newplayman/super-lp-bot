# PERMISSION_MATRIX — RH-00 完成时的权限与边界状态（2026-09-07）

| 项 | 状态 | 证据 |
|---|---|---|
| 签名 / 广播 / 私钥生成 | 0 / 0 / 0 | VPS `/etc/lpbot-executor/`、`/etc/lpbot-solana-executor/` keystore 与 password 均 0 字节（`reports/migration/…/VPS_INVENTORY.md`）；本机未复制任何 keystore；`grep -rnE '^\s*(import|from) (web3|eth_account|solders|solana)\b' scripts/` 零命中（`qwen/Q2_Q5_Q6_Q7.md` 题3） |
| `LIVE_TRADING` | false | `execution/base_m1_executor_v1.py:725`、`solana_m1_sidecar_v1.py:683`（B1 §7）；本机未启动任何执行器 |
| `lpbot-*` systemd 单元 | VPS 全部 disabled/inactive；本机不存在 | `reports/migration/…/stop/units_running_before.txt` |
| 旧四（实为五）个保护进程 | **已于 2026-09-07 12:02 UTC 在 VPS 停止**（用户本轮确认）；本机未启动 | `reports/migration/…/stop/` |
| 六常量 | 0.7 / 1.0 / 1.5 / 0.0005 / 0.001 / 0.50 不变 | `qwen/Q2_Q5_Q6_Q7.md` 题1 + 主脑 grep：`lp_multiwindow_stability:37`、`lp_netcover_engine:18,19,24,26`、`lp_netcover_inputs:94`；`lp_funnel_autopsy:46` 同值 0.70 重复定义（值相同，非旁路） |
| 100U / 50–60U / 40U / −5U / −10U | 不变 | 未触碰 `lp_stock_tier_policy`、allocator、配置 |
| 付费 RPC / 数据 | 0 | `lp_rpc_pool_v1_readonly.py:68-180` 免费端点表；本机未配置任何 key |
| `git push` | 0 | 本次仅本地 commit `279b047` |
| 删除 / 削弱测试 | 0 | pytest 3109/14 与 B1 相同；首轮 287 失败由路径布局造成，未改测试 |
| `scripts/lp_long_horizon/`、封存仓库 | 未动 | 封存仓库仅 tar 归档 `/root/lp-bot/_archive/` |
| 活库 VACUUM | 未对活库执行 | 只对 backup/静止副本 `VACUUM INTO` |
| 新三桶政策 | 未实现；`approved_for_live=false` 契约文件 `docs/rh_pivot/config.rh.shadow.example.toml` | — |
| 未授权、需用户签署 | 资本政策替代；执行开发/部署权限；限额真实资金试验（PRD §23） | — |

## 只读脚本对"钱包字样"的 17 处命中（题3）

全部为安全自证字段（`keystore_loaded: False`、`eth_sendTransaction_called: False`）、只读 docstring、禁词自检清单、RPC 方法名枚举、keystore 仅 stat 不读（`lp_c6_preflight:141-160`）。真实链库 import 与发送调用只存在于 `execution/`。

## 假绿点位复核（B1 §10.8，题4）

- `tests/test_lp_base_probe_dry_run_builder_v1_readonly.py:264`：函数体为 `for … : pass`，**无断言**，确认为 no-op 假绿；RH-08 回归包应补真实断言（不删）。
- `tests/test_lp_panel_server_v1_readonly.py:231`：无显式 assert，隐式"不抛异常"。
- `tests/test_lp_netcover_inputs_v1_readonly.py:777`：断言仅 `is not None`（:788-790）。
