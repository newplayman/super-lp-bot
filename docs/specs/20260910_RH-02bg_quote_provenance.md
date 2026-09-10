# RH-02bg：quote 证据的 provenance + TTL 校验（代码部分；实际数值等用户）

## 背景

`4cdfeb7` 让 `quote_usd_per_token1` fail-close（PRD:651 禁止强制按 $1），
后果是 **shadow 现在 200 步全无 NAV**。

调研结论在 `reports/AUDIT_quote_evidence_options_20260910.md`：

- **token1 确实是 USDG**（`0x5fc5360d0400a0fd4f2af552add042d716f1d168`，
  `rh_pool_registry` 实测 + `lp_rh_collector_v1_readonly.py:53-56`）。
- 仓库内**没有** USDG 的 REST 报价源，**也没有** USDG/USDC 参考池。
- 推荐方案 C：**带 provenance 与 TTL 的静态 quote**，
  依据 PRD:647-651 —— 禁止的是「强制按 $1」，不是「禁止低频/静态证据」。
- **脱锚 1% 的代价已量化**：`net_pnl` 从 −5.31 变 −15.26，
  多亏 9.95 美元 = 同期手续费收入的 **65 倍**。所以这条证据不是形式主义。

### ★调研点出的关键要求★

> 必须补 runner 的 provenance/expiry 校验；
> 否则只是把「缺失默认」改成了「无出处的显式数字」，不够合规。

**本包就是做这个校验。数值本身由用户提供，你不要编造。**

## 你要做的

### 一、定义 quote 证据的结构

在 `pool_meta` 中支持一个**结构化**的 quote 证据（而不是裸数字）：

```json
"quote_usd_per_token1": {
  "value": "<十进制字符串>",
  "source": "<来源标识，例如 coingecko:usdg-usd 或 onchain:pool 0x...>",
  "observed_at": "<RFC3339 UTC>",
  "ttl_secs": 86400
}
```

**同时向后兼容裸数字**：若是数字/字符串，视为**无出处证据** ——
按下面第二条的政策处理（默认拒绝，可用显式开关放行），
在报告里说明你选了哪种并给出理由。

### 二、runner 侧校验（`scripts/lp_rh_shadow_runner_v1_readonly.py`）

取 quote 时按顺序校验，任一不满足即 **fail-close**（该步无 NAV / 无 hodl）：

1. 证据存在；
2. `value` 可转 Decimal 且 `> 0` 且有限；
3. `source` 非空；
4. `observed_at` 可解析为 UTC 时间；
5. **未过期**：`该步的 sample_time - observed_at <= ttl_secs`。
   **注意用「该步样本自身的时刻」判断，不是墙钟时间** ——
   这是回放，必须问「在那一刻这条证据还有效吗」。
   （RH-02ab 已经为 gate 判定确立了同样的原则，照它的做法。）

过期与缺失要能区分：理由里分别点名
`QUOTE_EVIDENCE_MISSING` 与 `QUOTE_EVIDENCE_EXPIRED`。

### 三、不要写数值

**不许修改 `reports/lp_rh/pool_meta.json`**。
用户会自己填一条真实观测。你只交付代码 + 测试，
并在报告里给出**用户该填什么样子**的示例（用占位值，标注「示例，非真实观测」）。

## 不许动

`reports/` 下任何文件（含 `pool_meta.json`）、任何 `.db`、
`scripts/lp_silent_failure_lint_v1_readonly.py`、
`scripts/lp_rh_pool_attestation_backfill_v1.py`。

## 验收标准

1. 结构化证据 + 未过期 → 正常算 NAV，且数值与「裸数字同值」时**完全一致**
   （证明只是加了校验，没改算法）。
2. 缺失 → 无 NAV，理由 `QUOTE_EVIDENCE_MISSING`。
3. `observed_at` 距样本时刻超过 `ttl_secs` → 无 NAV，理由 `QUOTE_EVIDENCE_EXPIRED`。
4. **边界**：恰好等于 `ttl_secs` 时视为**未过期**（`<=`），写一条测试锁住。
5. `value <= 0`、非有限、`source` 为空、`observed_at` 不可解析 → 各一条测试，全部 fail-close。
6. **用真实 `pool_meta.json` 跑一次**：它当前没有 quote 键，
   所以应当 200 步全无 NAV 且理由是 `QUOTE_EVIDENCE_MISSING`。贴出实测。
7. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4624 passed / 0 failed**，不得新增 failed。

## 坑（今晚踩过，别再踩）

- `pool_meta.json` 里 `input_price_usd` 是**字符串** `"2484.0"` —— 取值要显式转换。
- 测试 fixture 必须与真实契约一致；至少一个用例走真实 `pool_meta.json`。
- 构造「过期」用例时，确认输入真的能走到过期分支
  （今晚有四次测试因输入触发不了缺陷而白测）。

## 纪律

- **不要执行任何 git 命令**，不要重启 daemon，不要动 crontab。
- 单次写入 ≤ 150 行。
