# Aerodrome Slipstream NPM 链上核验

结论：**PASS**。Base chain id=8453；签名 0、广播 0、钱包访问 0。

官方地址来源：<https://github.com/aerodrome-finance/slipstream#deployments>

| deployment | NPM | code bytes | SHA-256 | factory() | WETH9() |
|---|---|---:|---|---|---|
| initial | `0x827922686190790b37229fd06084350e74485b72` | 24542 | `e09412ee02e4f79b89361deabe1ab0e02c8cf2fb0db6f1cb27336fa15e8ee575` | `0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a` | `0x4200000000000000000000000000000000000006` |
| gauge_caps | `0xa990c6a764b73bf43cee5bb40339c3322fb9d55f` | 24542 | `fac3c73a57e633acde2a69cc33755f93ca4534faa31359bdc65e22bcb51c1562` | `0xade65c38cd4849adba595a4323a8c7ddfe89716a` | `0x4200000000000000000000000000000000000006` |
| gauges_v3 | `0xe1f8cd9ac4e4a65f54f38a5cdafca44f6dd68b53` | 24542 | `22efa538a3d6637271f081f1c2e7410a01a5c027ea6062feef0ab71005a4f783` | `0xf8f2eb4940cfe7d13603dddd87f123820fc061ef` | `0x4200000000000000000000000000000000000006` |

核验逻辑已经固化进 Base mainnet 执行器构造阶段：任一地址无代码、字节码长度/哈希不符，或 `factory()` / `WETH9()` 返回不符，启动立即失败，签名与广播路径不可达。
