# RH-02be：把「静默假绿」的识别手法做成仓库内的扫描工具

## 背景

这个项目已确认 **24 例**同一族缺陷：**不抛异常、数字照样出来、量级看着正常、结论全废**。
完整清单与识别手法在主脑记忆里，仓库内的证据在
`reports/AUDIT_silent_failure_hunt_20260909.md` 与
`reports/AUDIT_silent_failure_hunt2_20260909.md`。

**今晚一夜新增 8 例，其中 2 例是在修复别的缺陷时新造的**——
说明靠人工审计追不上产生速度，需要机器扫。

已有一个单点防线：`tests/test_no_module_level_decimal_pollution_v1_readonly.py`
（用正则 + AST 扫模块级 `getcontext().prec` 赋值）。**本包把这个思路推广开。**

## 你要做的

新建 `scripts/lp_silent_failure_lint_v1_readonly.py` + 对应测试。
用 **AST**（不要只用正则，正则会漏且会误报）扫描 `scripts/*.py`，报告下列模式：

### 规则 1：经济计算路径上的宽容默认值
`x.get(key, <数值字面量>)`，其中默认值是 `0`、`1`、`0.0`、`1.0`、`Decimal("0")` 等。
**危害**：缺数据被当成「值就是 0/1」。今晚实例：
`PRICES_USD.get(symbol, Decimal("0"))` 让未知代币价格为 0，成交量算成 0（-100%）；
`base_hist.get("p95_abs_drift", 700)` 让缺观测时用魔数 700（风险差 465 倍）。

### 规则 2：`bool(x.get("key"))` 形式的风险判断
**危害**：`key` 从不存在时 `bool(None)` 恒 `False`，风险闸门恒「安全」。
今晚实例：`chain_degraded` 等四个风险布尔，loader 从没放过这些键，闸门形同虚设。

### 规则 3：地址/哈希的大小写敏感等值比较
SQL 字符串里出现 `asset_address = ?` / `address = ?` / `pool = ?` 之类
而**没有** `LOWER(`。
**危害**：EVM 地址有 EIP-55 checksum 大小写形式，合法地址被判「无数据」。

### 规则 4：模块级全局状态修改
`getcontext().prec = N`、`locale.setlocale`、`warnings.filterwarnings`、
`sys.setrecursionlimit`、模块级 `os.environ[...] = ...`。
**危害**：import 即改全局，测试「单独跑绿、全量跑红」。
（已有的那个测试只查 `getcontext().prec`，把它的能力并进来。）

### 规则 5：`except` 里吞掉异常后返回数值
`except ...: return <数值>` —— 返回 0/1/常量而非 None 或重新抛出。
**危害**：错误被伪装成一个正常的数。

## 输出与用法

1. `--json` 输出结构化结果（供 CI 消费），默认输出人类可读的表格。
2. 每条命中给出：`文件:行号`、规则编号、命中的代码片段、**为什么危险**（一句话）。
3. `--fail-on-new` 模式：读取一份基线文件
   （`reports/silent_failure_lint_baseline.json`，你要生成它），
   **只有出现基线之外的新命中才返回非零退出码**。
   理由：存量命中有几百条，一次性清完不现实；
   **要挡住的是新增**。基线文件要入库。

## 硬要求：先自证有效

用今晚已修复的四个真实缺陷验证扫描器能抓到它们
（用 `git show <修复前 commit>:<文件>` 取修复前的源码喂给扫描器，**不要改任何文件**）：

```
规则 1  ->  4aa4497^:scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py
            （PRICES_USD.get(..., Decimal("0"))）
规则 1  ->  4aa4497^:scripts/lp_survival_out_of_range_risk_v1_readonly.py
            （base_hist.get("p95_abs_drift", 700)）
规则 2  ->  12efd38^:scripts/lp_rh_shadow_runner_v1_readonly.py
            （bool(sample.get("chain_degraded")) 等四处）
规则 4  ->  5efcde5^:scripts/lp_rh_exit_depth_v1_readonly.py
            （getcontext().prec = 80）
```

**四条都必须被扫出来**，把实际输出贴进报告。抓不到就说明规则写窄了，要放宽。

## 不许动

`scripts/lp_rh_*`、`scripts/lp_bsc_*`、`scripts/lp_survival_*`
（另一条线正在改其中几个）、任何 `.db`、`reports/` 下除你新建的基线文件外的任何文件。
既有测试**只允许新增**。

## 验收标准

1. 四条自证全部命中，原样输出贴进报告。
2. `--fail-on-new` 在当前基线下退出码为 0。
3. 人为在某个**新建的临时测试文件**里写一条违规（不要改既有文件），
   确认 `--fail-on-new` 返回非零；然后删掉那个临时文件。把过程写进报告。
4. 扫描全仓 `scripts/*.py` 的耗时 < 10 秒（贴出实测）。
5. 全量 `pytest tests/ -q -p no:cacheprovider | tail -3`，
   基线 **4602 passed / 0 failed**，不得新增 failed。

## 纪律

- **不要执行任何 git 命令**（`git show` 只读可用）。
- 不要重启 daemon，不要动 crontab，不要发真实网络请求。
- 单次写入 ≤ 150 行；不要整读 >300 行的文件。
