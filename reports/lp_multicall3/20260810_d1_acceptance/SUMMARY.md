# FIX-D1 Multicall3 验收证据

- 日期：2026-08-10
- 网络：Base mainnet
- 数据集：`reports/lp_funnel_autopsy/20260810_043427/stage1/screen.json` 中同一组 `gate_ok=true` 的 92 个池
- 安全边界：只执行 `eth_getCode` / `eth_call`；签名 0，广播 0；`eth_getLogs` 不在 Multicall3 能力范围内。

## 真实 resolver 读路径对照

同一 Python 进程内先跑原逐项 resolver 读，再跑 Multicall3 三波预取；两边均通过独立 `RpcPool("base")`，`RpcPool` 的底层 POST 被计数。比较字段包括 pool、factory/provenance、token0、token1、dec0、dec1、tick validation、contract code bytes 与失败分类。

| 指标 | 原逐项 eth_call | Multicall3 |
|---|---:|---:|
| 92 池 resolver 耗时 | 182.326 s | 21.613 s |
| 底层 HTTP RPC 尝试 | 1,297 | 130 |
| 其中 eth_call HTTP 尝试 | 1,196 | 23 |
| 其中 eth_getCode HTTP 尝试 | 101 | 107 |
| resolver 成功分类数 | 68 | 68 |
| 逐字段差异 | — | **0** |

实测改善：底层 HTTP 请求减少 **89.98%**（1,167 次），resolver 耗时减少 **88.15%**（160.713 秒，约 8.44 倍）。`eth_getCode` 不能由 aggregate3 承接，两个路径的少量差异来自免费端点底层重试次数，不是语义跳过。

Multicall3 本次逻辑调用 825 个：factory 440、pool identity 336、decimals 49；默认每批上限 60，形成 15 个 aggregate3 逻辑请求。底层实际出现 23 次 aggregate `eth_call` HTTP 尝试，体现 `RpcPool` 的轮巡/退避重试仍然有效。825 个子调用全部成功，cache hits=1,088，serial fallback=0。

## 启动链上校验

- address: `0xca11bde05977b3631167028862be2a173976ca11`
- validation_status: `VALIDATED`
- runtime bytecode: 3,808 bytes
- runtime bytecode Keccak-256: `0xd5c15df687b16f2ff992fc8d767b4216323184a2bbc6ee2f9c398c318e770891`

该地址不是“硬编码即信”：第一次批处理前必须通过同一个 `RpcPool` 调用 `eth_getCode`。空代码、读取错误或解码错误均记录 `FALLBACK_SERIAL` 与错误原因，并逐项回退 `eth_call`。

## 测试证据

- aggregate3 ABI 编解码 round-trip；每个 Call3 强制 `allowFailure=true`。
- 默认 batch=60；61 个调用分成 2 批。
- 单个子调用失败时相邻结果仍成功，失败不会吞掉整批。
- 启动 code 校验失败时显式记录并逐项回退。
- 两池 resolver 串行/批量字段完全一致，批量请求由 8 个串行 contract call 降为 3 个 aggregate request。
- scanner 两池 slot0/liquidity 批量读取；一个 slot0 失败不吞掉另一个池或同池 liquidity，缺失字段保持 fail-closed。

定向回归：`62 passed`（Multicall3 + resolver + scanner）。完整仓库回归与完整 scanner `--once` 总 cycle 对照由本轮总验收统一执行；本报告的耗时/请求数是 resolver 真实链上微基准，不冒充包含 `eth_getLogs` 的完整 cycle。
