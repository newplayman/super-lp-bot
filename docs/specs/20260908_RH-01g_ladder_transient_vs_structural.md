# RH-01g：`max_span` 阶梯必须区分瞬时故障与结构性上限

## 实测问题

RH-01f 上线后第一轮，ordofi 与 robinhood 的 `max_span` 都记成 **2000**。
但主脑随即手测（每级最多重试 3 次、间隔 6 秒）：

| 提供方 | 2000 块 | 5000 块 | 10000 块 |
|---|---|---|---|
| ordofi | 成功 2771 条 / 5.7s | **成功 7999 条 / 8.0s** | `-32005 network is busy`（3 次重试仍失败）→ **瞬时** |
| robinhood | 成功 2204 条 / 0.5s | **成功 7256 条 / 1.1s** | `logs matched by query exceeds limit of 10000` → **结构性** |

**两家的真实 `max_span` 至少是 5000，记成 2000 是低估。**
阶梯在 5000 那一级撞上一次瞬时错误就停了。

## 两个缺陷

1. **瞬时错误不重试**：一次 `-32005` 就把阶梯截断，永久低估该提供方。
2. **停止原因不记录**：`max_span=2000` 看起来像硬上限，实际可能只是一次抖动。
   两者的运维含义相反——结构性上限意味着「永远要拆到这个数以下」，
   瞬时意味着「重试即可」。

## 改哪些文件

只改 `scripts/lp_rh_provider_health_recorder_v1_readonly.py`，
测试追加进 `tests/test_lp_rh_provider_health_recorder_v1_readonly.py`。
**现有 46 条测试一条不许改、不许删**；若某条失败，停下来写明是哪条、为什么。

### 1. 瞬时错误分类（复用已有实现，不要重写）

`scripts/lp_rh_organic_recorder_v1_readonly.py` 里已有 `_is_transient(exc)`，
**import 它**，不要另写一份。若它不适用（签名或判据不符），
在报告里写明原因后再本地实现，并保持判据一致：
`-32005` / `network is busy` / HTTP 429 / HTTP 5xx / 超时 → 瞬时；
`exceeds limit` / `-32000` / `HTTP 403` / 参数错误 → 结构性。

### 2. 阶梯每级重试

每一级最多尝试 **3 次**，瞬时错误之间退避 `4/12` 秒（用可注入的 `sleep_fn`，
测试里注入假的，**测试不许真 sleep**）。三次仍失败才认为该级不可用。
**结构性错误立即停止，不重试。**

### 3. 记录停止原因

新增列 `max_span_limit_kind TEXT`，取值 `STRUCTURAL` / `TRANSIENT` / `NONE`：
- 某级因结构性错误失败 → `STRUCTURAL`
- 某级重试 3 次仍瞬时失败 → `TRANSIENT`
- 走完整个阶梯全部成功 → `NONE`（`max_span` 为阶梯最大值）
- 连最小级都失败 → `ok=0`，`max_span` 为 `NULL`，`max_span_limit_kind` 按实际原因填。

沿用 RH-01f 的 `_ensure_columns` 幂等加列，**不要 DROP 或重建表**。

## 新增测试（**≥10 条**）

- 5000 级结构性失败 → `max_span=2000`、`max_span_limit_kind="STRUCTURAL"`，
  且该级**只调用 1 次**（结构性不重试）。
- 5000 级瞬时失败 3 次 → `max_span=2000`、`kind="TRANSIENT"`，该级**调用 3 次**。
- 5000 级前两次瞬时、第三次成功 → `max_span` 继续推进到 10000，`kind="NONE"`。
  **这条直接复现主脑手测到的场景。**
- 全阶梯成功 → `max_span=10000`、`kind="NONE"`。
- 连 500 都结构性失败 → `ok=0`、`max_span is None`（**`is None` 断言**）、`kind="STRUCTURAL"`。
- 退避用注入的 `sleep_fn`，断言其被调用 2 次且**递增**；断言 `time.sleep` 未被真实调用。
- `_is_transient` 判据各举一例：`-32005`、HTTP 429、`exceeds limit`（非瞬时）、
  `HTTP 403`（非瞬时）。
- 旧库就地加 `max_span_limit_kind` 列且原有行不丢（幂等调用两次不报错）。
- 其他能力的 `max_span_limit_kind` 为 `NULL`。
- `CONSENSUS_METHODS` 回归断言：仍是那三项，不含 `log_range_max_span`、不含 `eth_blockNumber`。

## 不许动
不改其他脚本。不联网。测试不许真 sleep。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_provider_health_recorder_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥56 全绿（原 46 + 新增 ≥10）；全量 0 failed / 14 skipped。两条命令尾部原样贴出。
