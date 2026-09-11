# RH-02cj — 把 reorg 检测接成能跑的东西（T11）

## 背景

`scripts/lp_rh_reorg_resolution_v1_readonly.py` 与
`lp_rh_reorg_rollback_v1_readonly.py` 早就写好了，接口齐全：

```
ensure_table(conn)                      建 rh_reorg_contested
record_contested(conn, block_number=, ...)
resolve_contested(conn, block_number=, ...)
plan_rollback(conn, orphaned_block_hash=)
apply_rollback(conn, orphaned_block_hash=, ...)
```

**但没有任何生产路径调用它们**。实测：

```
rh_reorg_contested 表在 scanner.db 里不存在（从未被 ensure_table 创建过）
同一 block_number 出现多个 block_hash 的记录: 0 个
已采集 6880 个不同 block_hash / 6944 个不同 block_number
```

codex 在 PRD 对账里把 T11 标为「已实现且有测试 ⚠ 尚未接入完整端到端主链」。
采集器每轮记 `derived_block_number` / `derived_block_hash`
（`lp_rh_collector_v1_readonly.py:428-429`），原料一直在攒，没人去看。

**至今 0 个 reorg 不等于机制可用**——现在无从分辨「没发生过」和「发生了没人发现」。

## 唯一任务：一个只读检测器

新建 `scripts/lp_rh_reorg_detector_v1_readonly.py`。

```
python3 scripts/lp_rh_reorg_detector_v1_readonly.py \
    [--db reports/lp_rh/scanner.db] \
    [--out reports/lp_rh/REORG_SCAN.md] \
    [--record-db <path>]     # 给了才写 rh_reorg_contested，默认只报告不写
    [--json]
```

### 1. 从已采数据找分歧

扫 `rh_market_states`，找同一个 `derived_block_number` 对应**多个不同**
`derived_block_hash` 的情况。每组分歧输出：

- `block_number`
- 涉及的 hash 列表，各自的首次/末次 `sample_time` 与出现次数
- 时间跨度（两个 hash 的观测窗口是否重叠）

**反向检查也要做**：同一个 `derived_block_hash` 对应多个 `block_number`。
那不是 reorg，是数据损坏，必须单独报出来而不是混在一起。

### 2. `--record-db` 才写库

给了这个参数才调 `ensure_table()` + `record_contested()` 把分歧记进
`rh_reorg_contested`。**默认只报告不写**——与本仓库其它工具一致
（清理工具的 `--apply`、backfill 的 `--apply`）。

`record_contested` 的签名去模块里读，**不要猜参数名**。

### 3. 报告

`REORG_SCAN.md` 含：
- 扫描范围（行数、block_number 区间、时间区间）
- 分歧组数；**为 0 时明确写「未发现分歧」，不要写成「通过」**
  ——没发现和没有是两回事，报告要让读者看出这个区别
- 每组分歧的详情表
- 数据损坏（同 hash 多 number）单独一节
- 末尾一句：本扫描只覆盖**已采集的样本**，采集器不回查历史块，
  所以一次深度小于采样间隔的 reorg 可能根本没被观测到

退出码：发现分歧 → 1；未发现 → 0；扫描本身失败 → 2。

## 不许动

- **不要改采集器** `scripts/lp_rh_collector_v1_readonly.py`
  （接入持续检测是下一步，本包只做离线扫描）。
- 不要改 `lp_rh_reorg_resolution_v1_readonly.py` /
  `lp_rh_reorg_rollback_v1_readonly.py` 的任何行为，只调用它们。
- **不要调用 `apply_rollback`**。回滚会改数据，绝不在本包里发生。
- 不要碰 `scripts/lp_rh_shadow_runner_v1_readonly.py`（另一条线正在改）。
- 对生产库**只读**（`mode=ro`）；`--record-db` 指向的库在测试里只能是 `tmp_path`。
- **不要发任何网络请求。**
- **不要重启或 kill 任何进程**（采集器 1168725 / daemon 1789399 在跑生产）。
- **不要执行任何 git 命令。**
- 单次 Write ≤150 行或 6000 字符。

## 表的真实列（照抄）

```
rh_market_states 相关列: sample_time, derived_block_number, derived_block_hash
rh_reorg_contested: 去 lp_rh_reorg_resolution_v1_readonly.py 的 CREATE TABLE 读
```

## 测试（`tests/test_lp_rh_reorg_detector_v1_readonly.py`）

内存库或 `tmp_path` 造数据，**不碰真实库**。

1. 造 3 个样本，同 `block_number=100`，两个不同 hash → 检出 1 组分歧，
   报告里列出两个 hash 及各自的观测次数。
2. 全部 block_number 各自唯一 hash → 检出 0 组，退出码 0，
   报告里出现「未发现分歧」而**不是**「通过」字样。
3. 同一 hash 对应两个 block_number → 归入**数据损坏**一节，不计入 reorg 分歧。
4. `derived_block_number` 或 `derived_block_hash` 为 NULL 的行被跳过，
   不计入任何一类（**不要当成分歧**）。
5. 不给 `--record-db` → `rh_reorg_contested` 表**不被创建**。
6. 给了 `--record-db` → 表被创建且分歧被写入，条数与检出组数一致。
7. 重复跑 `--record-db` 幂等（`record_contested` 用的是 INSERT OR IGNORE，
   第二次不新增行）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_reorg_detector_v1_readonly.py -q` 全绿，条数 ≥ 7。
2. 真实库上跑（**不给 --record-db**）：
   ```
   python3 scripts/lp_rh_reorg_detector_v1_readonly.py --db reports/lp_rh/scanner.db --out /tmp/REORG.md
   ```
   退出码 0（当前数据无分歧），报告生成。把扫描范围与结论那几行贴进总结。
3. 跑完后 `rh_reorg_contested` 表在生产库里**仍然不存在**：
   ```
   python3 -c "import sqlite3;c=sqlite3.connect('file:reports/lp_rh/scanner.db?mode=ro',uri=True);print([r[0] for r in c.execute(\"select name from sqlite_master where name='rh_reorg_contested'\")])"
   ```
   输出 `[]`。
4. `git status --short` 里只有这两个新文件是 `??`。
