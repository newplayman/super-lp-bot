# FIX-E3 Solana sidecar 验收摘要

- 安全契约与构建/模拟管线的确定性验收：`32 passed`（本轮实跑
  `python3 -m pytest tests/test_solana_m1_sidecar_e3.py -q`）。
- dry-run 报告契约包含 C5 对齐字段：五检、交易 message、program runtime evidence、simulation result、`signed=false`、`broadcast_count=0`、`keystore_loaded=false`。
- 免费 Solana mainnet RPC 的 `getAccountInfo` 实测：Raydium AMM v4、Raydium CLMM、Orca Whirlpool 三个白名单程序在同一 slot `438427989` 均为 `executable=true`，owner 均为 upgradeable BPF loader；原始结构化证据见 `PROGRAM_VERIFICATION.json`。
- 本分项未伪造候选、钱包余额或 quote/basis：没有经 E1/E4/E7 验收的具体池计划，因此没有把“假余额 + 任意指令”的公网 simulation 标成候选 dry-run 通过。真实候选出现后可由 `scripts/lp_solana_m1_dry_run_v1_readonly.py` 完成构建和 `simulateTransaction`，该入口没有 signer 或 `sendTransaction` 路径。
- 主机已创建独立 `lpbot-solana-executor` nologin 用户；配置/状态目录 0700，keystore/password 是 0600、0 字节空占位，策略用户不可读。unit 已安装但保持 disabled/inactive；证据见 `HOST_ISOLATION.json`。
- 本轮没有生成私钥/钱包，没有读取 keystore，没有签名，没有广播，没有启动 systemd unit。
