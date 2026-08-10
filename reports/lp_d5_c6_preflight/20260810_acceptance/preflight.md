# C6 preflight（只读）

结论：**FAIL**；PASS 6 / FAIL 2。

| 条件 | 结果 | 证据摘要 |
|---|---:|---|
| 存在 ≥1 个全闸通过候选 | FAIL | latest=2026-08-10T11:07:11.047908+00:00; accepted=0 |
| C4 广播锁 false 且未解锁 | PASS | runtime_locked=True; LIVE_TRADING_true=False; startup_confirmed=False; unit_default_false=True; send_calls=0 |
| keystore 权限与进程隔离 | PASS | keystore=True; password=True; distinct_users=True; contents_read=false |
| kill switch 与 EXIT_ONLY 通路 | PASS | mint_blocked=True; revoke_allowed=True |
| 下破退出演练 C3 | PASS | verdict=derived; scenarios=3; all_pass=True |
| 账本对账工具可用 | PASS | base_live_impl=True; operator_cli_stub=False |
| 免费 RPC 健康且无 EXIT_ONLY/KILLED | PASS | chain_id=8453; block=49786412; state=NORMAL; unresolved=0 |
| 钱包余额与 gas 储备（若配置） | FAIL | 未配置钱包/余额探针；未访问钱包、未读取 keystore |

缺失证据按 FAIL 处理。脚本不读取 keystore 内容；本次 signed=false、broadcast_count=0。
