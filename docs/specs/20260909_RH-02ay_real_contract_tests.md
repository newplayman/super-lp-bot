# RH-02ay：把「用真实配置文件跑一次」固化成测试

## 为什么要做（今晚刚被咬了一口）

`RH-02ai` 交付时带 **6 个新测试全绿**，但**生产路径第一次调用就抛 `TypeError`**：

```python
position_liquidity_raw(float(position_usd), pool_meta["input_price_usd"], ...)
```

`reports/lp_rh/pool_meta.json` 里 `input_price_usd` 存的是**字符串** `"2484.0"`，
而所有 fixture 都写 float `2484.0`。`position_liquidity_raw` 内部
`if entry_price <= 0` 拿 str 和 int 比，直接崩。

主脑是在验收时**用真实 pool_meta 跑了一次**才发现的。若只信 worker 自带测试，
这个 commit 会带着一个必崩的生产路径入库，而且 shadow daemon 要等**下次重启**
才崩——届时没人会想到是这个 commit。

这是本项目已确认的第 14 类缺陷（fixture 与真实契约不符），**已复发多次**。

## 你要做的：新建一份「真实契约测试」

新建 `tests/test_real_config_contract_v1_readonly.py`，**只新建这一个文件**。

它要做三件事：

### 一、锁定真实配置文件里每个键的类型

读 `reports/lp_rh/pool_meta.json`（用 `json.load`，**不要自己手写 dict**），
对下列键断言其 Python 类型与当前实际一致：

```
input_price_usd   str      "2484.0"      ← 注意是字符串
range_pct         float    10.0
dec0              int      18
dec1              int      6
gas_usd_estimate  float
tvl_usd           float
liquidity         int
sqrt_price_x96    int
current_tick      int
tick_spacing      int
fee_pips          int
attestation_status str
protocol          str
tick_data         list
```

**先自己跑一遍确认实际类型**（`python -c` 打印 `type(v).__name__`），
以实际为准；上表是主脑实测的，若有出入以你实测的为准并在报告里说明。

这个测试的意义：**当有人改了采集器、让某个键的类型变了，这里会立刻红**，
而不是等到某个消费者在生产里崩。

### 二、用真实 pool_meta 驱动每个消费者，断言不抛异常

`grep -rn 'pool_meta' scripts/*.py | grep -v test | head -30` 找出所有消费者。
对每一个能独立调用的函数，用**真实 pool_meta**（不是 fixture）调一次，
断言：**不抛异常**，且返回值不是 None（除非该函数在缺数据时本就该返回 None）。

至少要覆盖：
- `scripts/lp_rh_shadow_runner_v1_readonly.py` 的 `run_episode`
  （用 `load_samples_from_db` 从真实 `reports/lp_rh/scanner.db` 取 20 条样本驱动）
- `scripts/lp_rh_exit_depth_v1_readonly.py` 的 `exit_depth_for_size`
  （照 `shadow_runner:288` 的方式构造 pool_state：整个 pool_meta 减去
  `attestation_status`/`protocol`/`max_impact_bps` 三个键）

**注意**：这些测试要能在没有网络的环境下跑（只读本地文件与 db）。
若真实 db 不存在，用 `pytest.skip` 跳过并写明原因，**不要让测试假装通过**。

### 三、一条通用防御：数值型配置不得是无法转换的类型

对 pool_meta 里所有**应当是数值**的键，断言 `float(v)` 或 `int(v)` 不抛异常。
这样即使将来类型从 str 变 float（或反过来）测试仍绿，
但变成 `None`/`"N/A"`/`""` 这类会立刻红。

## 不许动

**任何既有文件都不许改**——本包只新建一个测试文件。
特别注意 `scripts/lp_rh_shadow_runner_v1_readonly.py` 另有一条线在改，绝对不要碰。
不要动 `.db`、不要动 `pool_meta.json`。

## 验收标准

1. `/root/lp-bot/.venv/bin/python -m pytest tests/test_real_config_contract_v1_readonly.py -q -p no:cacheprovider`
   全绿，把原样输出贴进报告。
2. **自证有效**：把 `input_price_usd` 的类型断言故意改成 `float`，
   确认测试会红（证明它真的在检查），然后**改回来**。把这个过程写进报告。
3. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`：
   基线是 **4529 passed / 0 failed**，不得新增 failed。
4. `git status --short | grep -v '^??'` 应为**空**（你只新建文件，不改既有文件）。

## 纪律（违反即退回）

- **不要执行任何 git 命令**。
- 不要重启 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件，用 `sed -n 'a,bp'`。
- 命令输出只贴尾部。
