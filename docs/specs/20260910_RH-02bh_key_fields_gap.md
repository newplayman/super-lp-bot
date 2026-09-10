# RH-02bh：Stage A 的 `KEY_FIELDS_INCOMPLETE` 到底缺什么、怎么补（只调研）

## 背景

`5f23276` 把 PRD §21.1 的七项硬指标接进 Stage A 闸门后，真实库报出 5 个 blocker。
其中 `STAGE_A_KEY_FIELDS_INCOMPLETE` 是**数据缺失**，不是代码问题：

- `reports/AUDIT_stage_a_prd_reconciliation_20260909.md` 实测：
  **10 列全 NULL**（`reference_bid`/`reference_ask`/`multiplier_human`/`oracle_paused` 等），
  `fee_growth_global_0/1` **仅 9.2% 非空**（费率列是 09-09 当天才加的）。

**本包只调研，不改任何代码、不采任何数据。**

## 你要回答的

### 一、逐列现状（用真实库实测）

对 `reports/lp_rh/scanner.db` 的 `rh_market_states`，**逐列**统计：
非空率、不同值个数、最早/最新非空时刻。
把结果按非空率从低到高列成表。

对非空率 < 100% 的每一列，判定属于哪一类：

- **A 类：采集器本该填但没填**（有 writer、有取值路径，但值没进去）
- **B 类：需要新数据源才能填**（例如需要 REST，而采集器 docstring 明写「no REST here」）
- **C 类：语义未定义**（PRD 没规定该填什么，属产品决策缺口而非工程缺陷）
- **D 类：正确为空**（该场景下本就不该有值）

**每一类都要给出判定依据**（采集器的 文件:行号、PRD 行号、或实测数据）。

### 二、闸门实际要求哪几列

`scripts/lp_rh_readiness_v1_readonly.py` 里的 key-field 检查
（`grep -n 'key_field\|audit_key_field_health' scripts/lp_rh_readiness_v1_readonly.py`）
**具体检查哪几列、阈值是多少**？
这几列的现状分别是什么？**哪一列是当前真正卡住闸门的那个**？

### 三、补齐路径（按代价排序）

对 A 类：采集器要改哪里？（文件:行号）
对 B 类：需要接什么源？要不要 key？是否计费？
对 C 类：PRD 里有没有相关表述？若没有，明确列为「需用户产品决策」，
并给出你建议的定义（供用户裁决）。

**特别关注 `fee_growth_global_0/1` 的 9.2%**：
- 它是 09-09 才加的列，之前的样本没有，这是**历史缺口**还是**持续问题**？
- 用 mtime / sample_time 分布判断：**加列之后的样本，非空率是多少**？
  若加列后接近 100%，那它只是等时间；若仍有缺口，是采集器有问题。
  **这个区分决定了它属于「等时间」还是「要修」。**

### 四、Stage A 距离通过还差多少

综合本包与已知的其它 blocker，给一张表：
每个 blocker | 属于「等时间」还是「要动手」| 若要动手，动什么 | 预估代价。

## 交付

**在 `reports/` 下新建** `reports/AUDIT_key_fields_gap_20260910.md`。

**除了创建这一个新文件，不许改动仓库里任何文件。**
不要执行任何 git 写命令，不要重启进程，不要动 .db，不要采任何数据。

## 注意

- 本机无 `sqlite3` 命令行，用 python 的 `sqlite3` 模块。
- **不要递归扫描 `reports/`**（12.5 万文件，会撑爆上下文）。
- 需要读 PRD 时用 `grep -n` 定位后只读命中处上下 40 行，
  **不要整读** `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md`（9 万字）。

## 纪律

- **不要执行任何 git 命令**，不要重启 daemon，不要动 crontab，不要发真实网络请求。
