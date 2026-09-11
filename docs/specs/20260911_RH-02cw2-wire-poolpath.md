GOAL:
把 `pool_meta_path` 从 daemon 接到 `run_episode`。现在参数加了、逻辑写了、测试绿了,
但**生产调用方从不传它**,所以生产里那段代码是死的。

## 现象(已实测,直接用)

刚落地的改动给 `run_episode` 加了可选参数 `pool_meta_path`
(`scripts/lp_rh_shadow_runner_v1_readonly.py:811`),用它在
`_resolve_pool_state_as_of`(390 行)里取 pool_meta 文件的 mtime 作为池态时间戳。

但 daemon 的 `_episode_kwargs` 没传:

```
scripts/lp_rh_shadow_daemon_v1_readonly.py  _episode_kwargs(...)
    return dict(strategy_episode=..., samples=..., position_usd=...,
                horizon_hours=..., capital_usd=..., target_mode=...,
                now_fn=now_fn, pool_meta=cfg["pool_meta"])
                                    ↑ 没有 pool_meta_path
```

实测后果:主脑手工跑一轮,30/30 条 gate decision 的 `reasons_json` 里是
`POOL_STATE_AS_OF_UNAVAILABLE`,`cost_components_json` 里
`pool_state_source` 恒为 `"UNAVAILABLE"`。
因为 `pool_meta.json` 的 `as_of` 与 `observed_at` **都是 None**,
`FILE_MTIME` 是唯一可用来源,而它拿不到路径。

daemon 本来就有这个路径:`--pool-meta-json` 是必填参数(534 行),
`PoolMetaProvider(args.pool_meta_json)`(549 行)。

## 要做的事

只改 `scripts/lp_rh_shadow_daemon_v1_readonly.py` 与
`tests/test_lp_rh_shadow_daemon_v1_readonly.py`(若无此测试文件,则加到
`tests/test_lp_rh_shadow_runner_v1_readonly.py`)。

1. 把 pool_meta 的**文件路径**放进 `cfg`,并在 `_episode_kwargs` 里传给 `run_episode`。
   - **先读 `cfg` 是怎么构造的**(看 `main()` 里怎么组装、`PoolMetaProvider` 怎么用),
     按既有惯例加,不要发明新结构。
   - `_episode_kwargs` 的 docstring 写着「scratch 与 ledger 两个分支必须传完全相同的参数」——
     **确保两条分支都拿到它**(它们共用这个函数,所以加对地方就自动满足,但要确认)。
2. 路径拿不到时传 `None`,**保持现有的 fail-close**(`POOL_STATE_AS_OF_UNAVAILABLE`),
   不要编造时间戳、不要回退到「当前时间」——那会让一个 31 小时前的池态看起来是新鲜的。

## 关键:这一条测试才是本包的交付物

> **断言 daemon 跑完一轮之后,落库的 `cost_components_json` 里
> `pool_state_source == "FILE_MTIME"`(而不是 `"UNAVAILABLE"`)。**

必须**通过 daemon 的入口**跑(`run_one_round` 或 `_run_episode_persisted`),
**不要直接调 `run_episode` 然后自己把路径传进去** ——
那正是上一轮漏掉这个缺陷的原因:测试绕过了真实调用方。

配套再加一条:路径为 `None` 时仍是 `UNAVAILABLE`(fail-close 未被破坏)。

## 不许动

- 不要改 `run_episode` 的签名或 `_resolve_pool_state_as_of` 的逻辑(它们已经对了)。
- 不要改 `POOL_STATE_STALE_SECS`,不要让陈旧变成阻断。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要碰 `scripts/lp_rh_quote_refresh_v1.py`(另一个任务在建它)。
- **不要修改 `reports/lp_rh/pool_meta.json`**。不要写 `reports/lp_rh/` 下的任何数据库;
  测试用 `tmp_path`,用仓库自己的 `migrate()` 建 schema。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_lp_rh_shadow_runner_v1_readonly.py -q`(全绿)
2. `grep -n "pool_meta_path" scripts/lp_rh_shadow_daemon_v1_readonly.py`(应有传参)
3. 报告里贴出那条新测试的代码片段,并说明它是**从 daemon 入口**跑的
4. **不要跑全量测试**(另有 worker 并行跑,会撞车)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
