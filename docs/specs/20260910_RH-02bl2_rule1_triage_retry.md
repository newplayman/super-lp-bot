# RH-02bl-2 — 规则1 命中分级（重派，换掉上一轮做砸的输入方式）

## 上一轮为什么退回

上一轮（RH-02bl）产出的 `reports/rule1_triage_20260910.json` **数量凑够了 248，
但身份对不上**。主脑做集合差分：

```
分级表与基线的 (file, line, fingerprint) 三元组：
  基线独有 66 条   分级独有 65 条
```

抽样看差异，是**行号偏移**：

```
分级表写   lp_tier_c_exit_feasibility_v1_readonly.py:391
实际扫描是 lp_tier_c_exit_feasibility_v1_readonly.py:408
分级表写   test_stage_supervisor_..._v1.py:308
实际扫描是 test_stage_supervisor_..._v1.py:307
```

原因是**靠人工/模型去「对照」基线里的条目**，而不是原样搬运。
分级结论再准，锚不到具体代码行就没法拿去改。

**上一轮的分析质量本身是好的**——它判出的那条 A 级
（`lp_rh_shadow_runner_v1_readonly.py:460`，`pool_meta.get("max_impact_bps", 50)`）
主脑已核实：行号正确、判断正确，那行确实在 `position_and_exit_depth_pass`
闸门路径上。所以本轮**不要推翻它的判断逻辑，只换输入方式**。

另外：基线 `reports/silent_failure_lint_baseline.json` **已经漂移**
（今晚改过代码），当前实时扫描 249 条 rule1、基线只有 244 个唯一身份。
所以本轮**以实时扫描为准，不要读基线**。

## 输入：先生成，再逐条搬运

**第一步，必须先跑这条命令**（不要跳过，不要凭记忆写条目）：

```bash
python3 scripts/lp_silent_failure_lint_v1_readonly.py --json > /tmp/rule1_input.json
```

然后从 `/tmp/rule1_input.json` 的 `hits` 数组里筛出 `rule == 1` 的条目。
字段是 `file` / `line` / `col` / `rule` / `fingerprint` / `snippet`
（注意是 `file`，不是 `path`）。

**这几个字段一律原样复制，一个字符都不要改、不要重新定位、不要「修正」行号。**
你只负责在每条上**添加**分级字段。

处理方式建议：写一个小 python 脚本读入、加字段、写出，
**不要手工逐条敲 JSON**——上一轮就是手工搬运出的错。
脚本可以放在 `/tmp` 下，不要留在仓库里。

## 分级定义（与上一轮相同，不要自创等级）

- **A（热路径 / 必须修）**：命中所在函数从下列任一入口**可达**，
  且默认值参与数值计算、阈值比较、或闸门布尔判定。
- **B（热路径 / 需确认）**：可达入口，但默认值只影响日志、报告文案、
  或已在别处 fail-close 的分支。
- **C（冷路径）**：不可达入口。仓库里有大量 RH 转向**之前**的旧线脚本
  （BSC 费率速度、Meteora DLMM、Polymarket 竞品、tier_b/tier_c 回放、
  portfolio paper runner 等），不参与当前 shadow / 毕业判定。
- **D（误报）**：语法上是 `get(k, default)` 但语义上不是宽容默认
  （默认值就是唯一正确语义，或紧跟显式 None 检查）。

### 热路径入口（判可达性只用这三个）

1. `scripts/lp_rh_shadow_runner_v1_readonly.py` — 影子运行器，daemon 正在跑
2. `scripts/lp_rh_readiness_v1_readonly.py` — Stage A/B 毕业闸门
3. `scripts/lp_rh_v3_inventory_v1_readonly.py` — Uniswap V3 库存/估值数学

可达性 = 从这三个文件出发，沿 `import` 与函数调用**传递闭包**。
不确定时按更严的一级判（宁可判 A/B 也不要漏成 C）。

**特别注意**：上一轮 248 条里只判出 1 条 A 级，而
`lp_rh_shadow_runner_v1_readonly.py` 这一个文件就有 5 条规则1 命中。
请对这三个入口文件**自身**的每一条命中都逐条给出判定与理由，
不要因为「看起来无害」就一律扫进 C。

## 产出（两个文件）

### 1. `reports/rule1_triage_20260910.json`

```json
{
  "generated_at": "<UTC ISO8601>",
  "input_source": "scripts/lp_silent_failure_lint_v1_readonly.py --json (live scan)",
  "code_version": "<git rev-parse --short=12 HEAD 的输出>",
  "rule1_count": 249,
  "entry_points": ["scripts/lp_rh_shadow_runner_v1_readonly.py", "..."],
  "summary": {"A": 0, "B": 0, "C": 0, "D": 0},
  "hits": [
    {
      "file": "<原样>", "line": 0, "col": 0, "fingerprint": "<原样>", "snippet": "<原样>",
      "enclosing_function": "<函数名，模块级写 __module__>",
      "grade": "A",
      "missing_key": "<被 get 的键名>",
      "default_value": "<默认值字面量>",
      "reachable_from": ["scripts/lp_rh_shadow_runner_v1_readonly.py"],
      "call_path": "shadow_runner.main -> a.b -> c.d",
      "impact": "一句话：这个默认值会让什么数算错",
      "reason": "为什么定这一级"
    }
  ]
}
```

`hits` 条数**必须等于实时扫描里 rule==1 的条数**。
C/D 级的 `call_path` 可为空串，但 `reason` 必须写。

### 2. `reports/AUDIT_rule1_triage_20260910.md`

中文报告：
- 四级各多少条、占比
- **A 级逐条列表**（表格：文件:行 / 被吞的键 / 默认值 / 会算错什么 / 建议改法）
  ——核心产出，每条要能让人直接照着改
- **三个入口文件自身命中的逐条判定**（单独一节，无论判成什么级）
- B 级按文件汇总
- C 级只给「文件 → 条数」汇总 + 一句话说明属于哪条已废弃旧线
- D 级列出并说明为何误报（将来可加进扫描器白名单）
- 结尾：**如果只有时间修 5 条，修哪 5 条，为什么**

## 硬性约束

- **只读分析**。除上面两个产出文件外，不许修改仓库任何文件。
  尤其不许改 `scripts/`、`tests/`、`reports/silent_failure_lint_baseline.json`。
- **不要执行任何 git 命令**（`git rev-parse --short=12 HEAD` 这一条只读查询
  是本包要求的，允许；但不要 add / commit / checkout / stash）。
- 不要"顺手修复"你判为 A 级的缺陷——这一包只出清单。
- 单次 Write ≤150 行或 6000 字符，JSON 大就分次追加写，或用脚本生成。
- 不要整读超过 300 行的文件；用 `sed -n 'X,Yp'` 读命中附近，`grep -n` 找调用关系。

## 验收标准（主脑会逐条查，上一轮就是栽在第 2 条）

1. `reports/rule1_triage_20260910.json` 存在，`hits` 条数 = 实时扫描 rule1 条数。
2. **把 JSON 里的 `(file, line, fingerprint)` 集合与
   `python3 scripts/lp_silent_failure_lint_v1_readonly.py --json` 实时输出中
   rule==1 的同名集合做差集，两边都必须为空。**
3. `summary` 四数之和 = `hits` 条数，且与实际 grade 分布一致。
4. 每条 A/B 级都填了非空的 `call_path`、`impact`、`missing_key`。
5. 三个入口文件自身的每一条命中都在 Markdown 报告里有逐条判定。
6. `git status --short` 里除这两个产出文件外，没有任何已跟踪文件被改动。
