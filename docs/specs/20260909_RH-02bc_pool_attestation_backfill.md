# RH-02bc：补采当前 CORE 池的 attestation（只写脚本 + dry-run，不执行采集）

## 背景：这是 Stage A 毕业的实打实阻断项

`RH-02az`（commit `5f23276`）把 PRD §21.1 的七项硬指标接进了 Stage A 闸门后，
真实库报出 6 个 blocker，其中一条**不是等时间能解决的**：

```
STAGE_A_POOL_NOT_ATTESTED
```

实测：当前观测的 CORE 池 `0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca`
在 `rh_contract_attestations` 里**一条记录都没有**。
`rh_assets` 有 194 行但**全是股票代币，没有池的底层代币**（WETH / USDG）。
`rh_pool_registry` 只有 1 行，且缺 `hooks` / `pool_id`。

PRD §21.1 条件 4「身份和能力证据清楚」要求这些证据齐备。

## 你要做的（只做前两步，第三步留给用户授权）

### 一、先调研清楚既有机制（**不要自己发明**）

1. `rh_contract_attestations` 的表结构与主键：
   `grep -n 'rh_contract_attestations' -A 20 scripts/lp_rh_store_v1_readonly.py`
   （已知主键含 `block_hash`，所以同一地址在不同区块有多行，这不是重复）
2. **现有的 attestation 是谁写进去的**？
   `grep -rln 'rh_contract_attestations' scripts/ | head`
   找到那个采集器，读它怎么取证、怎么落库、字段含义是什么。
   **补采脚本必须复用它的取证逻辑，不要另写一套**——
   同一个量的多个实现是这个项目已确认 22 例缺陷的温床。
3. `rh_assets` 的结构，以及池底层代币应该以什么形态入库。

### 二、写补采脚本

新建 `scripts/lp_rh_pool_attestation_backfill_v1.py`（**注意不带 `_readonly` 后缀**，
因为它会写库；参考仓库里其它写库脚本的命名与结构）。

要求：

1. **默认 `--dry-run`**：只打印将要采集哪些地址、将要写入哪些行，**不发任何网络请求、不写库**。
   `--apply` 必须显式指定才会真正执行。
2. 目标地址：池合约 + 它的 token0 / token1（从 `rh_pool_registry` 读，
   若缺 `token0`/`token1` 则从 `reports/lp_rh/pool_meta.json` 或链上补，
   **在 dry-run 输出里说明每个地址是怎么确定的**）。
3. **同块取证**：attestation 的价值在于「同一个区块高度上的一致快照」，
   现有数据的 `attestation_status` 是 `ATTESTED_SAME_BLOCK`。
   照既有采集器的做法，在同一个 block 上取全部地址的证据。
4. **幂等**：重复运行不产生重复行（主键含 block_hash，天然按块去重；
   在报告里说明你验证过这一点）。
5. **RPC 预算**：在 dry-run 输出里**估算这次补采要发多少次 RPC 调用**。
   这是要给用户看的数字——他要据此决定是否授权。

### 三、★不要执行 `--apply`★

**本包只交付脚本与 dry-run 输出。** 实际采集会消耗 RPC 预算、写生产库，
属于需要用户本轮确认的动作。你跑 `--dry-run` 即可，
把输出原样贴进报告。**跑了 `--apply` 就算违反 spec。**

## 验收标准

1. `--dry-run` 输出包含：目标地址清单（含每个地址的来源）、
   预计写入的表与行数、**预计 RPC 调用次数**。原样贴进报告。
2. 脚本在 `--dry-run` 下**不发任何网络请求**——
   用 `grep` 证明网络调用都在 `--apply` 分支里，或在报告里说明你怎么保证的。
3. 新增测试：dry-run 不写库（跑前跑后 `rh_contract_attestations` 行数不变）。
4. 新增测试：缺少 token0/token1 时**明确报错**，不要静默跳过或写入空地址。
5. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4582 passed / 0 failed**，不得新增 failed。

## 不许动

`scripts/lp_rh_shadow_runner_v1_readonly.py`、`scripts/lp_v3_fee_share.py`、
`scripts/lp_netcover_inputs_v1_readonly.py`、`scripts/lp_bsc_*`、`scripts/lp_survival_*`
（另外两条线正在改这些）、任何既有 `.db`、`reports/` 下任何文件。

## 坑（今晚踩过，别再踩）

- `reports/lp_rh/pool_meta.json` 里 `input_price_usd` 是**字符串** `"2484.0"`，
  取任何配置值都要显式转换并 fail-close。
- 写 `x.get("key")` 前先确认 `key` 真的会出现在 `x` 里——
  今晚两个 worker 分别栽在这上面，**测试全绿而生产必崩**。
- 测试至少要有一个用例走真实文件/真实 db，不要全用手写 fixture。

## 纪律

- **不要执行任何 git 命令**。
- **不要执行 `--apply`**，不要重启 daemon，不要动 crontab。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件。
