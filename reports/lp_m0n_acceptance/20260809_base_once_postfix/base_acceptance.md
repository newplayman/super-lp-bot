# TP-M0N Base `--once` 正式验收

结论：**PASS，accepted=0 如实保留**。本批次运行于 `a08b74f` 终闸修复之后；旧目录 `20260809_base_once` 是修复前中止批次，0 score，不参与证据。

## 锁定证据

```text
[scanner] as_of=2026-08-09T16:14:33.474230+00:00 screened=730 top=30 resolved=30 scored=30 accepted=0 sessions=0
[tg-fallback] event=rpc_degraded text=[LPBOT][WARNING][rpc_degraded] scanner RPC health changed UNKNOWN -> DEGRADED; new entries blocked
[scanner] vetted_menu exported=0 invalid=0 out=reports/lp_m0n_acceptance/20260809_base_once_postfix/vetted_menu.json
```

| 文件 | SHA-256 |
|---|---|
| `scanner.db` | `1e546b7a61f5b104ddba6b20fa65c8b402ab3550981db6daf394b151db1be8ea` |
| `vetted_menu.json` | `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570` |
| `gate_report.json` | `b7a71eed7078118becea5950c8899b6374e44841999c2b8f3494f79787d54ad9` |
| `gate_report.md` | `eb7dcae804cb07bd078bc26cbe7e04e1ceac9dfb34239ae949a666326cf4208e` |

DB 以 `mode=ro&immutable=1` 交叉核对：730 snapshots、30 scores、30 reward observations、16 finite NetCover、14 entry eligible、0 NetCover PASS、0 vetted、0 accepted。Persistence 为 STRONG 12、WEAK 16、fee-only NOT_APPLICABLE 2；source 为 surrogate 28、absent 2、measured 0。当轮 30 条 observation 全为 `defillama:/pools`，只在判定完成后落盘，没有给同轮自证。

终态理由为：14 条 historical `PERMANENT_FAIL_CLOSED:ambiguous_multi_factory_pool`（工程状态 `blocked_pending_authoritative_pool_mapping`）、9 条 `NETCOVER_BELOW_SHADOW`、7 条 `ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK`。

## 目标池变化

- MSUSD-USDC `aae6cc3a…` / `0x7501…10fb`：M0F `MISSING` → M0N `SURROGATE_STRONG`、factor 0.25、entry true；最终 NetCover `0.419744309`，理由 `NETCOVER_BELOW_SHADOW`。
- canonical USDC-CBBTC `ff82c362…` / `0x4e96…e778`：M0F `MISSING` → M0N `SURROGATE_WEAK`、factor 0、entry false；NetCover `0.107043792`，理由 `ENTRY_INELIGIBLE:REWARD_PERSISTENCE_SURROGATE_WEAK`。
- 另外两条同名 USDC-CBBTC `6f1786fc…` / `c0675357…` 无 resolved pool，保持权威映射阻断；没有按 symbol 猜池。

## 30 条逐池证据

`id` 是 DefiLlama pool UUID 前 8 位；`S/W/N` 分别表示 STRONG/WEAK/fee-only NOT_APPLICABLE。RPC `DEGRADED` 是 cycle 级观测，不冒充下表某条 score 的拒绝原因。

| # | symbol | id | pool | tier/factor | entry | NetCover | accepted | terminal reason |
|---:|---|---|---|---|---:|---:|---:|---|
| 1 | AERO-CBBTC | 53b7036a | — | W/0 | false | — | false | mapping blocked |
| 2 | AVNT-USDC | eb27d0be | 0xe30d…5dcb | S/.25 | true | .109192 | false | NetCover below |
| 3 | CBETH-CBBTC | 79369b35 | — | W/0 | false | — | false | mapping blocked |
| 4 | EURC-USDC | 847c874f | 0xe846…0ec7 | W/0 | false | .083670 | false | entry weak |
| 5 | EURC-USDC | fbce5857 | — | W/0 | false | — | false | mapping blocked |
| 6 | MSUSD-MSETH | 3fea9aec | — | W/0 | false | — | false | mapping blocked |
| 7 | MSUSD-USDC | aae6cc3a | 0x7501…10fb | S/.25 | true | .419744 | false | NetCover below |
| 8 | RECALL-USDC | 4e01eb90 | — | S/.25 | true | — | false | mapping blocked |
| 9 | USDC-CBBTC | ff82c362 | 0x4e96…e778 | W/0 | false | .107044 | false | entry weak |
| 10 | USDC-CBBTC | 6f1786fc | — | W/0 | false | — | false | mapping blocked |
| 11 | USDC-CBBTC | c0675357 | — | W/0 | false | — | false | mapping blocked |
| 12 | USDC-CBMEGA | f9fbb53c | 0x0150…6e83 | W/0 | false | .127211 | false | entry weak |
| 13 | USDC-PROS | 9e788cd1 | 0x8a8e…e4e | S/.25 | true | .124802 | false | NetCover below |
| 14 | USDC-USDT | ba557f7e | 0xa41b…fcd1 | W/0 | false | .007086 | false | entry weak |
| 15 | USDC-VELVET | c07a115f | 0x6b0f…a1be | W/0 | false | .000014 | false | entry weak |
| 16 | USDC-VVV | c7d461f8 | 0x67a1…6530 | N/1 | true | .788733 | false | NetCover below |
| 17 | WETH-AAVE | 2641aaa3 | 0x4a79…f1b | S/.25 | true | .064818 | false | NetCover below |
| 18 | WETH-AERO | 3aebe700 | — | S/.25 | true | — | false | mapping blocked |
| 19 | WETH-BRETT | e92866f1 | 0x4e82…ba02 | S/.25 | true | .249643 | false | NetCover below |
| 20 | WETH-CBBTC | d632293f | 0x7aea…bd1 | N/1 | true | .393463 | false | NetCover below |
| 21 | WETH-CBBTC | 07eda095 | — | W/0 | false | — | false | mapping blocked |
| 22 | WETH-CBBTC | 541b4974 | — | W/0 | false | — | false | mapping blocked |
| 23 | WETH-CBXRP | ad247753 | — | S/.25 | true | — | false | mapping blocked |
| 24 | WETH-EURC | deeb8740 | — | W/0 | false | — | false | mapping blocked |
| 25 | WETH-MORPHO | f884e3f7 | 0xb5f0…288c | S/.25 | true | .098673 | false | NetCover below |
| 26 | WETH-MSETH | 08e1a166 | 0x74f7…0c0e | S/.25 | true | .048336 | false | NetCover below |
| 27 | WETH-USDC | 1328ac9d | — | S/.25 | true | — | false | mapping blocked |
| 28 | WETH-USDT | 577caee3 | 0x9785…3c1b | W/0 | false | .325353 | false | entry weak |
| 29 | WETH-USOL | a09feb82 | 0x0225…98a1 | W/0 | false | .017846 | false | entry weak |
| 30 | WETH-VVV | 7185982b | — | S/.25 | true | — | false | mapping blocked |

Gate 为 `INSUFFICIENT_EVIDENCE`：0 position identities、0 root pools，只有未关闭严重 RPC incident `=0` 子闸 PASS。菜单内容为 `[]`；没有用 fixture、阈值放宽或默认值制造 accepted。
