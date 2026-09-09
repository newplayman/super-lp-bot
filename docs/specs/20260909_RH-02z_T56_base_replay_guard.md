# RH-02z：T56 —— 回放能力早就有了，缺的是「差异=0」的证据

## PRD 要求

`§20 T56`：`旧Base模型同一SQLite快照新旧计算 → 未批准的逐闸结果差异=0`
属「原工程保护」需求族（§0／§2／§22），审计判为 **需关注：无实现**。

## 但能力已经存在

`scripts/lp_netcover_snapshot_replay_v1_readonly.py`（80 行）：
```
"""Replay NetCover gates from a SQLite snapshot without touching its source DB."""
def replay(*, db_path: Path, code_root: Path) -> dict[str, Any]
```
其注释写明：*"This lets TP-J compare pre/post source on one copied snapshot."*
——正是 T56 的语义。**缺的是把它变成常驻的回归证据。**

主脑已实测（2026-09-09）：
```
replay(db_path='reports/lp_m0f_acceptance/20260809/scanner.db',
       code_root='/opt/lpbot/lp-bot-v3-origin-check')
  -> 返回键 ['code_root','db','netcover_pass_counts','position_cap_counts','row_count','rows']
     row_count = 30
     netcover_pass_counts  = {"False": 30}
     position_cap_counts   = {"False": 14, "True": 16}
  源库 md5 前后一致（只读性成立）
```
快照 696K，含 733 行 `pool_snapshots` 与 30 行 `opportunity_scores`，是**真实 Base 数据**。

## 只新建两个文件（golden 基线 + 测试）

### 1. `tests/data/t56_base_replay_golden.json`
由测试**首次运行时不得自动生成**——必须由本包一次性写入并入库，
内容是对上述快照回放结果的**规范化**形式：

- 保留：`row_count`、`netcover_pass_counts`、`position_cap_counts`，
  以及 `rows` 中每行的**判定相关字段**。
- **必须剔除环境相关字段**：`code_root`、`db`（绝对路径随机器变化）。
- `rows` 按稳定键排序后再序列化（如按 `as_of` + 池标识），
  用 `json.dumps(..., sort_keys=True)`，浮点统一为字符串或定点，
  **避免平台浮点表示差异造成假失败**。

### 2. `tests/test_lp_rh_t56_base_replay_guard_v1_readonly.py`（≤240 行，**≥12 测试**）
顶部 `import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')`。**不许联网。** 必测：

- **★对同一快照调 `replay`，规范化后与 golden 文件**逐字段相等**；
  不等时的失败信息必须打印出**具体哪个字段、哪一行**不同
  （不是一句 "dicts differ"）★**——这是 T56 的「差异=0」
- **★源库只读：回放前后快照文件的 md5 完全一致★**
- `row_count == 30`（锚定实测值）。
- `netcover_pass_counts == {"False": 30}`（锚定实测值）。
- `position_cap_counts == {"False": 14, "True": 16}`（锚定实测值）。
- golden 文件里**不含** `code_root` 与 `db` 两个键（两条断言，防止把本机路径固化进仓库）。
- 连续两次 `replay` 结果相同（确定性；若含时间戳字段则排除后比较）。
- 快照文件存在且大小 > 0（前置断言，缺文件时给出可读信息而不是 KeyError）。
- 规范化函数对浮点的处理是稳定的：同一数值两次规范化得到相同字符串。
- `replay` 在 `db_path` 不存在时抛出可识别异常而非静默返回空结果。
- golden 文件是合法 JSON 且顶层是 dict。
- **测试不得在缺 golden 时自动写入**：断言当 golden 缺失时测试失败并提示
  「基线缺失，需人工审核后生成」——**基线更新必须是人的决定，不是测试的副作用**。

## 不许动
不改 `lp_netcover_snapshot_replay_v1_readonly.py`、
不改 `lp_netcover_inputs_v1_readonly.py`、不改 `lp_netcover_engine_v1_readonly.py`
（**它们正是被保护的对象，改了就失去意义**）。
不改任何 RH 模块。不改快照文件。不联网。
单次 Write/Edit ≤150 行或 6000 字符；写完 `ast.parse` 自检。

## ★这个包的意义★
它保护的不是新功能，而是**旧工程**：将来任何人改动 NetCover 闸门，
若无意中改变了对旧 Base 快照的判定，这个测试会红。
**「未批准的差异 = 0」中的「未批准」意味着：基线的每一次变更都必须是人明确决定的，
所以测试绝不能自动重写基线。**

## 验收
```
/root/lp-bot/.venv/bin/python -m pytest tests/test_lp_rh_t56_base_replay_guard_v1_readonly.py -q -p no:cacheprovider
/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
定向 ≥12 全绿；全量 **0 failed / 14 skipped**。两条命令尾部原样贴出。
