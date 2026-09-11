GOAL:
删掉一个**被接受但从不使用**的参数 `pool_meta_path`。这是个小包,纯删除。

## 现象(已实测)

`rh-02cw3` 去掉了 FILE_MTIME 这个池态时间戳来源之后,
`_resolve_pool_state_as_of` 的函数体里**再也没用过** `pool_meta_path`:

```
scripts/lp_rh_shadow_runner_v1_readonly.py:388-411
    def _resolve_pool_state_as_of(pool_meta, pool_meta_path=None):
        ...函数体只读 pool_meta 的三个键，pool_meta_path 一次都没出现...
```

但它仍然被一路串下来:

```
scripts/lp_rh_shadow_runner_v1_readonly.py:390   函数签名
scripts/lp_rh_shadow_runner_v1_readonly.py:803   run_episode 的参数
scripts/lp_rh_shadow_runner_v1_readonly.py:809   传给 _resolve_pool_state_as_of
scripts/lp_rh_shadow_runner_v1_readonly.py:1751  main() 里传 a.pool_meta_json
scripts/lp_rh_shadow_daemon_v1_readonly.py:230   _episode_kwargs 传 cfg.get(...)
scripts/lp_rh_shadow_daemon_v1_readonly.py:512-513  从 provider 补进 cfg
scripts/lp_rh_shadow_daemon_v1_readonly.py:560   cfg 初始化
```

**这是个假信号。** 下一个人看到「路径已经从 daemon 接到 runner 了」,
会合理地推断「所以池态时间戳一定用了文件 mtime」——而那正是
`rh-02cw3` 刚刚判定为「朝危险方向说谎」并移除的做法。
留着这条死线路,等于给下次复发铺好了路。

## 要做的事

把 `pool_meta_path` 从上述全部位置删干净,包括:
- `_resolve_pool_state_as_of` 的形参
- `run_episode` 的形参与它对 `_resolve_pool_state_as_of` 的传参
- `run_episode` 的 `main()` 里的传参
- daemon 的 `_episode_kwargs`、cfg 初始化、以及 512-513 行那段从 provider 补路径的逻辑
- 测试里所有传这个参数的地方

**注意**:daemon 的 `--pool-meta-json` 命令行参数**要保留**,
它是 `PoolMetaProvider` 用来读文件的,与本包无关。只删 `pool_meta_path` 这条传递链。

删完确认:`grep -rn "pool_meta_path" scripts/ tests/` **无输出**。

## 不许动

- 不要改 `_resolve_pool_state_as_of` 的优先级逻辑(三个键的顺序)或返回值语义。
- 不要改 `POOL_STATE_STALE_SECS`、不要让陈旧变成阻断。
- 不要改 `PoolMetaProvider`、不要动 `--pool-meta-json` 命令行参数。
- **绝对不要修改 `scripts/lp_rh_collector_v1_readonly.py` 或 `scripts/lp_rh_store_v1_readonly.py`**
  ——动它们会把 Stage A 的 72 小时判定窗口清零。
- 不要碰 `scripts/lp_rh_reconciliation_v1.py`(另一个任务正在改它)。
- 不要修改 `reports/lp_rh/pool_meta.json`,不要写 `reports/lp_rh/` 下的任何数据库。
- **不要执行任何 git 命令。不要 kill 或重启任何进程**
  (PID 2271374 采集器、2685886 shadow daemon 在跑生产)。
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试

不需要新增测试逻辑,但**现有那几条池态测试必须继续全绿**,
特别是这两条(它们是 rh-02cw3 的交付物,删参数不能把它们弄坏):
- 「pool_meta 三个时间戳字段都没有 → 落库 `pool_state_source == "UNAVAILABLE"`」
- 「touch pool_meta 文件不改变任何结果」

如果有测试是靠传 `pool_meta_path` 来构造场景的,**改成通过 pool_meta 字典本身构造**,
不要为了让测试通过而把参数留着。

## ENVIRONMENT(照做,别自己找解释器)
- 直接用 `python3`(3.12.3 + pytest 7.4.4 + pycryptodome,本仓库钉死的版本)。
- **不要找 venv**(`/root/lp-bot/.venv` 无权限)。**不要 pip install**。**不要改任何全局配置**。
- 不要读 `reports/polymarket_competitor`。不要整读 >300 行的文件。

## VALIDATION(命令与输出尾部原样贴进报告)
1. `grep -rn "pool_meta_path" scripts/ tests/`(**必须无输出**)
2. `grep -n "pool-meta-json\|pool_meta_json" scripts/lp_rh_shadow_daemon_v1_readonly.py`(命令行参数**仍在**)
3. `python3 -m pytest tests/test_lp_rh_shadow_daemon_v1_readonly.py tests/test_lp_rh_shadow_runner_v1_readonly.py -q`(全绿)
4. **不要跑全量测试**(另有 worker 并行跑)。主脑会统一跑。

最后按以下字段报告:TASK_STATUS, SUMMARY, FILES_CHANGED, COMMANDS_RUN, TESTS_RUN, TEST_RESULT, UNRESOLVED, RISKS, NEXT_STEP。
