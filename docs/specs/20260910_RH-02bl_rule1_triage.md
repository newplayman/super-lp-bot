# RH-02bl — 规则1（宽容默认值）248 条命中分级

## 背景（必读，决定判据）

`scripts/lp_silent_failure_lint_v1_readonly.py` 是本仓库的「静默假绿」防复发扫描器。
规则1 = **宽容默认值**：`d.get(k, <默认值>)` 之类，键缺失时不报错、悄悄用一个默认值继续算。

这类写法本身不是缺陷。它变成缺陷的条件是：
**缺失的键落在经济计算或毕业闸门判定路径上，默认值让程序算出一个"看着正常"的错数字，
不抛异常、不打日志、量级不离谱，于是结论全废。**

本仓库已确认 24 例此类缺陷，其中最严重的一例让手续费收益虚高 **1022 倍**
（`fee_growth` 量纲错误，隐含年化 29076% 被当成真实收益）。

基线 `reports/silent_failure_lint_baseline.json`（`hits` 数组）里规则1 有 **248 条**，
分布在 **62 个文件**。它们目前**全部被基线豁免**（扫描器只对新增命中报警）。
问题是：这 248 条里混着"无害的 UI 默认值"和"下一个 1022 倍"，没人分过。

## 任务

对基线里 `rule == 1` 的全部 248 条命中逐条定级，产出可执行的整改清单。

### 分级定义（严格按此，不要自创等级）

- **A（热路径 / 必须修）**：该命中所在函数，从下列任一入口**可达**，
  且默认值参与数值计算、阈值比较、或闸门布尔判定。
- **B（热路径 / 需确认）**：可达上述入口，但默认值只影响日志、报告文案、
  或已在别处 fail-close 的分支。
- **C（冷路径）**：不可达上述入口。仓库里有大量 RH 转向**之前**的旧线脚本
  （BSC 费率速度、Meteora DLMM、Polymarket 竞品、tier_b/tier_c 回放、
  portfolio paper runner 等），它们不参与当前 shadow / 毕业判定。
- **D（误报）**：语法上是 `get(k, default)` 但语义上不是宽容默认
  （例如默认值就是唯一正确语义、或紧跟着显式 None 检查）。

### 热路径入口（判可达性用这三个，不要扩大）

1. `scripts/lp_rh_shadow_runner_v1_readonly.py` — 影子运行器，daemon 正在跑它
2. `scripts/lp_rh_readiness_v1_readonly.py` — Stage A 毕业闸门
3. `scripts/lp_rh_v3_inventory_v1_readonly.py` — Uniswap V3 库存/估值数学

可达性 = 从这三个文件出发，沿 `import` 与函数调用**传递闭包**能到达命中所在的函数。
不确定时按更严的一级判（宁可判 A/B 也不要漏判成 C）。

## 产出（两个文件，只写这两个）

### 1. `reports/rule1_triage_20260910.json`

```json
{
  "generated_at": "<UTC ISO8601>",
  "baseline_version": 2,
  "baseline_rule1_count": 248,
  "entry_points": ["scripts/lp_rh_shadow_runner_v1_readonly.py", "..."],
  "summary": {"A": 0, "B": 0, "C": 0, "D": 0},
  "hits": [
    {
      "file": "scripts/xxx.py",
      "line": 123,
      "fingerprint": "<原样抄基线里的>",
      "snippet": "<原样抄基线里的>",
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

`hits` 必须**恰好 248 条**，且每条的 `file`/`line`/`fingerprint` 与基线逐字对应。
C 级和 D 级的 `call_path` 可以留空字符串，但 `reason` 必须写。

### 2. `reports/AUDIT_rule1_triage_20260910.md`

中文报告，包含：
- 四级各多少条、占比
- **A 级逐条列表**（表格：文件:行 / 被吞的键 / 默认值 / 会算错什么 / 建议改法）
  ——这一节是整个任务的核心产出，务必写透，每条都要能让人直接照着改
- B 级按文件汇总（不必逐条展开）
- C 级只给「文件 → 条数」汇总表 + 一句话说明这些属于哪条已废弃的旧线
- D 级列出并说明为何是误报（这些将来可以从扫描器里加白名单）
- 结尾：**如果只有时间修 5 条，修哪 5 条，为什么**

## 硬性约束

- **只读分析**。除上面两个产出文件外，**不许修改仓库任何文件**。
  尤其不许改 `scripts/`、`tests/`、`reports/silent_failure_lint_baseline.json`。
- **不要执行任何 git 命令**（不要 add / commit / checkout / stash）。入库是主脑裁决后的动作。
- 不要"顺手修复"你判为 A 级的缺陷——这一包只出清单，修复另派。
- 单次文件写入 ≤150 行或 6000 字符，更大的文件分次追加写。
- 不要整读超过 300 行的文件；用 `sed -n 'X,Yp'` 只读命中附近，用 `grep -n` 找调用关系。
- 读基线用：`python3 -c "import json;d=json.load(open('reports/silent_failure_lint_baseline.json'));print(len([h for h in d['hits'] if h['rule']==1]))"`
  基线条目字段是 `file` / `line` / `col` / `rule` / `fingerprint` / `snippet`（注意是 `file` 不是 `path`）。

## 验收标准（主脑会逐条查）

1. `reports/rule1_triage_20260910.json` 存在，`hits` 长度**恰好 248**。
2. 把 JSON 里的 `(file, line, fingerprint)` 三元组集合与基线里 `rule==1` 的同名集合
   做差集，**两边差集都为空**。
3. `summary` 四个数之和 = 248，且与 `hits` 里实际的 grade 分布一致。
4. 每条 A 级都填了非空的 `call_path`、`impact`、`missing_key`。
5. `git status --short` 里除这两个新文件外**没有任何其它已跟踪文件被改动**。
6. Markdown 报告里 A 级逐条列表的条数 = JSON 里 A 级条数。
