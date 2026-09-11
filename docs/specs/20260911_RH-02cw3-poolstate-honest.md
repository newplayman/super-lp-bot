GOAL:
修掉一个**朝危险方向说谎**的指标。这是主脑上一个 spec 的设计错误,不是实现问题。

## 现象(已实测)

刚接线的池态陈旧度指标,用**文件 mtime** 当池态观测时间:

```
_resolve_pool_state_as_of 的优先级:  as_of → observed_at → 文件 mtime → UNAVAILABLE
```

主脑在 `2026-09-11T13:41:35Z` 用 `lp_rh_quote_refresh_v1.py` 刷新了
`pool_meta.json` 里的 **quote 字段**(只改了 quote,其他字段逐字节未变)。
结果从 daemon 入口实跑,落库的是:

```
pool_state_source    = FILE_MTIME
pool_state_as_of     = 2026-09-11T13:41:35Z     ← 看起来很新鲜
pool_state_age_secs  = -289.290408              ← 负数
```

**但池子状态本身(`sqrt_price_x96` / `liquidity_raw` / `tvl_usd`)根本没被刷新,
它们仍然是 2026-09-10 06:39 观测的,已经 31 小时。**

`pool_meta.json` 是个多字段文件:刷新其中**任何一个**字段,都会把**所有**字段的
表观年龄重置为零。于是这个本来用来暴露陈旧的指标,反而会把陈旧藏起来。
这比没有这个指标更糟——它会让人以为自己在看一个新鲜的池态。

## 要做的事

只改 `scripts/lp_rh_shadow_runner_v1_readonly.py` 与对应测试。

### 1. 去掉 FILE_MTIME 这个来源

新的优先级:
1. `pool_meta["pool_state_observed_at"]` → source `"POOL_STATE_OBSERVED_AT"`
2. `pool_meta["as_of"]` → source `"AS_OF"`
3. `pool_meta["observed_at"]` → source `"OBSERVED_AT"`
4. 其余一律 → source `"UNAVAILABLE"`,`as_of` 与 `age_secs` 都是 `None`,
   并追加原因码 `POOL_STATE_AS_OF_UNAVAILABLE`

**不要再读文件 mtime。** `run_episode` 的 `pool_meta_path` 参数若因此不再需要,
就把它连同 daemon 侧的传参一起删干净(**不要留一个没人用的参数**);
若你判断保留更好,在报告里说明理由。

**`UNAVAILABLE` 是当前的正确答案。** 池态字段没有自己的时间戳,
诚实的结论就是「不知道有多旧」,而不是编一个看起来新鲜的数字。

### 2. 负数年龄要当异常

即使将来有了真时间戳,也可能出现 `sample_time` 早于池态观测时间的情况。
`age_secs < 0` 时:
- 照实记录那个负数(**不要 clamp 成 0**,那会抹掉证据)
- 追加原因码 `POOL_STATE_AS_OF_IN_FUTURE:<秒数取整>`
- **不要**同时追加 `POOL_STATE_STALE`

### 3. 不要动的

- `POOL_STATE_STALE_SECS = 21600` 不变,陈旧仍然**不阻断**开仓。
- 不要改 `pool_meta.json`(**一个字段都不要加、不要改**)。
  `pool_state_observed_at` 这个字段现在不存在,代码要能正确处理它不存在的情况——
  这正是测试要覆盖的主路径。
- 不要改 `leg_fraction` / `organic` / 任何成本数值 / 任何闸位判定。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要写 `reports/lp_rh/` 下的任何数据库或文件;测试用 `tmp_path`,用仓库自己的 `migrate()` 建 schema。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试(≥6 条;改掉原来那几条依赖 FILE_MTIME 的)

**必须从 daemon 入口跑并查库**,不要直接调 `run_episode` 自己喂参数——
上一轮正是因为测试绕过真实调用方,漏掉了一个生产里完全没接上的缺陷。

1. **当前生产形态**:pool_meta 三个时间戳字段都没有 →
   落库 `pool_state_source == "UNAVAILABLE"`,`as_of`/`age_secs` 都是 `None`,
   `rh_gate_decisions.reasons_json` 里**查得到** `POOL_STATE_AS_OF_UNAVAILABLE`
2. 有 `pool_state_observed_at` 且很旧 → source 正确,`POOL_STATE_STALE:<秒>` 落库
3. 有 `pool_state_observed_at` 且很新 → 无 STALE 原因码
4. `as_of` 与 `observed_at` 的优先级各一条
5. **池态时间戳晚于 sample_time** → `age_secs` 是**负数原值**,原因码是
   `POOL_STATE_AS_OF_IN_FUTURE:`,且**没有** `POOL_STATE_STALE`
6. 防复发:**改写 pool_meta 文件的 mtime(touch 一下)不得改变任何结果**
   —— 这条专门钉死「刷新 quote 不会让池态看起来变新鲜」

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_lp_rh_shadow_runner_v1_readonly.py -q`(全绿)
2. `grep -n "FILE_MTIME\|st_mtime\|getmtime" scripts/lp_rh_shadow_runner_v1_readonly.py`(**应无输出**)
3. 报告里贴出第 1 条和第 6 条测试的代码片段,并说明它们是**从 daemon 入口**跑、**断言查的是数据库**
4. **不要跑全量测试**(另有 worker 并行跑)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
