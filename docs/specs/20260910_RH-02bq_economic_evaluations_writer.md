# RH-02bq — 把每步算出来的经济结果落进 `rh_economic_evaluations`

## 缺陷（已由 codex 定位 + 主脑核实，不要重新调研）

`scripts/lp_rh_shadow_runner_v1_readonly.py` 的主循环里，第 508 行已经算出了
完整的 NetCover 经济结果：

```python
record = assemble_rh_clmm_inputs(_evidence_for(sample, pool_meta),
                                 position_usd=position_usd,
                                 horizon_hours=horizon_hours)
gated = apply_netcover_gate([record])[0]
```

同一轮循环随后写了两张表（L659-678）：`rh_gate_decisions`、`rh_position_marks`。
**但 `gated` 里的经济数字一个都没落库。**

后果：`rh_economic_evaluations` 至今 **0 行**。PRD Stage B 要求的
「实际全成本 / NetCover 门槛 / OOS / 最差日 / 不确定性」全部依赖这张表
（依据 `docs/rh_pivot/PRD_RH_LP_Bot_v1.1_CN.md:1074-1076`、`540-547`）。

daemon 已经跑了 113 个 episode、4,487 步通过终闸，**一条经济记录都没留下**。

## 唯一任务：在 runner 里加一个 writer

在 `insert_row(conn, "rh_gate_decisions", {...})` **之后**、
`rh_position_marks` 写入**之前**，插入一条 `rh_economic_evaluations`。

### 表结构（已核实，照抄）

```sql
CREATE TABLE rh_economic_evaluations (
    candidate_key TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    horizon_hours INTEGER NOT NULL,
    position_usd TEXT NOT NULL,
    fee_ev TEXT,
    reward_ev TEXT,
    cost_components_json TEXT,
    netcover TEXT,
    abs_profit TEXT,
    q_min TEXT,
    q_max TEXT,
    missing_inputs_json TEXT,
    evaluated_at TEXT NOT NULL,
    derived_block_hash TEXT,
    derived_block_number INTEGER,
    PRIMARY KEY (candidate_key, snapshot_id, model_version, policy_version,
                 horizon_hours, position_usd)
)
```

### 第一步：先确认 `gated` 的真实字段名

动手写映射之前，先跑一次把键打出来（**不要靠猜**）：

```bash
python3 -c "
import importlib.util
def L(p,n):
    s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ni=L('scripts/lp_rh_netcover_inputs_v1_readonly.py','ni')
ne=L('scripts/lp_netcover_engine_v1_readonly.py','ne')
import inspect; print([k for k in inspect.getsource(ne.apply_netcover_gate).split() if 'netcover' in k][:20])
"
```
或者更直接：在 runner 里临时 `print(sorted(gated.keys()))` 跑一次单测看输出，
拿到真实键名后再写映射，然后把临时 print 删掉。

### 字段映射规则

- `candidate_key` ← `decision.candidate_key`
- `snapshot_id` ← `sample.get("source_payload_hash")`
  （`rh_market_states` 的每样本唯一标识；**为 `None` 时不要写这一行**，
  跳过并在 step 里记一个原因，不要伪造一个 id）
- `horizon_hours` ← `horizon_hours`（转 `int`）
- `position_usd` ← `str(position_usd)`
- `fee_ev` / `reward_ev` / `netcover` / `abs_profit` ← 从 `gated` 取对应键，
  **一律 `str(...)` 存，`None` 就存 `None`**
- `cost_components_json` ← `json.dumps(<gated 里的成本分项>, sort_keys=True)`
- `missing_inputs_json` ← `json.dumps(gated.get("missing_inputs") or [], sort_keys=True)`
- `q_min` / `q_max` ← `gated` 里若无对应键就存 `None`
  （size interval 模块尚未接线，**不要自己算一个填进去**）
- `evaluated_at` ← 与 `rh_gate_decisions` 同一时刻（`decision.decided_at`），
  保证两张表能按时间对齐
- `derived_block_hash` / `derived_block_number` ← `sample.get(...)` 同名字段
- `model_version` / `policy_version` ← 从 `gated` / `pool_meta` 里取；
  **确实取不到时用明确的常量字符串**（如 `"rh_clmm_v1"` / `"unknown_policy"`），
  但要在代码注释里写清这是占位、来源待接线

### 三条硬性语义

1. **缺失一律写 `None`，绝不写 `0` 或空字符串。**
   本仓库今晚已确认 26 例「静默假绿」，全部源于「没有证据却填了个看着正常的值」。
2. **不要捕获 `sqlite3.IntegrityError`。** 同一样本跨轮重跑会撞主键，
   这个冲突要让它抛出去，由 daemon 层统一统计（那是 RH-02bp 的职责）。
   同一轮内每个样本的 `source_payload_hash` 不同，不会自撞。
3. **不要因为写这张表而改变任何既有行为**：
   step 的 eligible 判定、NAV 计算、gate/mark 写入全部保持原样。

## 不许动

- **不要改 `scripts/lp_rh_shadow_daemon_v1_readonly.py`**（另一条线 RH-02bp 正在改它）。
- 不要改 `scripts/lp_rh_readiness_v1_readonly.py` 或它的测试（另一条线在改）。
- 不要改 `scripts/lp_netcover_engine_v1_readonly.py` 或
  `scripts/lp_rh_netcover_inputs_v1_readonly.py`——**只读取它们的输出**。
- 不要改经济公式、NAV 公式、`inventory_for_position`——今晚刚修好并与
  独立参考实现对齐到 1e-26，动一下就白费。
- **不要真的去写 `reports/lp_rh/scanner.db`**；测试一律用内存库或 `tmp_path`。
- **不要重启、不要 kill 任何正在跑的 daemon 进程**。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。
- 单次 Write/Edit ≤150 行或 6000 字符。
- 不要整读这个 900 行的文件；用 `grep -n` 定位，`sed -n '500,520p'`、
  `sed -n '650,690p'` 读需要的片段。

## 测试（追加到 `tests/test_lp_rh_shadow_runner_v1_readonly.py`）

用内存库或 `tmp_path`，不碰真实库。

1. 跑一个小 episode（复用该文件里已有的 fixture/样本构造方式）后，
   `rh_economic_evaluations` 行数 **> 0**，且等于
   `rh_gate_decisions` 的行数减去被跳过的（`source_payload_hash` 为 None 的）步数。
2. 取任一行，断言 `netcover` 与该步 `gated["netcover"]` 的字符串一致
   ——**证明落库的是真值，不是占位**。
3. 构造一个 NetCover 输入缺失的样本 → 该行的
   `missing_inputs_json` 非空数组，且 `netcover` 为 `None`
   （**不是 `"0"`，不是 `""`**）。这条是本包的 fail-close 核心。
4. `source_payload_hash` 为 `None` 的样本 → **不写这一行**，
   且 episode 不崩、其它步照常写。
5. `evaluated_at` 与同一步的 `rh_gate_decisions.decided_at` **相等**
   （证明两表可按时间对齐）。
6. 既有行为零回归：随便挑该文件里两条现有测试，确认仍然通过
   （不用新写，跑一遍即可）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_shadow_runner_v1_readonly.py -q` 全绿，新增 ≥5 条。
2. `grep -n "rh_economic_evaluations" scripts/lp_rh_shadow_runner_v1_readonly.py`
   能看到 `insert_row` 调用。
3. `grep -n "IntegrityError" scripts/lp_rh_shadow_runner_v1_readonly.py` **无输出**
   （不许捕获主键冲突）。
4. 全量 `python3 -m pytest tests/ -q` 通过。
5. `git status --short` 里只有
   `scripts/lp_rh_shadow_runner_v1_readonly.py` 和
   `tests/test_lp_rh_shadow_runner_v1_readonly.py` 被改动
   （其它文件的既有改动状态不能被你改变）。
