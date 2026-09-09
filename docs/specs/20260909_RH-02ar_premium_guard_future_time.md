# RH-02ar：报价新鲜度检查把「未来时间戳」判为 FRESH

## 铁证（主脑已核实）

`scripts/lp_rh_premium_guard_v1_readonly.py:131-134`：

```python
age_secs = int((now_dt - gen_dt).total_seconds())
if age_secs <= max_age_secs:
    return "FRESH", age_secs
return "STALE", age_secs
```

`generated_at` 晚于 `now` 时 `age_secs` 为**负**，负数当然 `<= 60`，
于是**一个尚未生成的报价被判定为「新鲜」**。
审计复现：领先 1 小时的时间戳返回 `("FRESH", -3600)`。

docstring 明写「age 从服务端 generatedAt 起算（PRD §8.1）」，
意图是防陈旧数据；但负龄意味着**时钟不一致或数据源有问题**，
这种情况下最不该做的就是判定为新鲜。

## 你要做的

给未来时间戳设一个**小容差**，超出即判为不可信：

- `-tolerance <= age_secs <= max_age_secs` → `FRESH`
- `age_secs < -tolerance` → 返回 `("INVALID", age_secs)`
  （不要返回 STALE——它不是陈旧，是时间方向错了，两者的处置不同）
- `age_secs > max_age_secs` → 仍是 `STALE`（原行为不变）
- 容差取 `5` 秒，做成带默认值的关键字参数 `future_tolerance_secs: int = 5`，
  理由写进 docstring：NTP 漂移与服务端/本地时钟差在秒级属正常，小时级不是。

**顺带检查同文件其它用 `(now - t)` 算年龄的地方**有没有同一问题，
有就一并修，没有就在报告里写明查过哪几处。

## 不许动

任何其它 `scripts/`（多条线正在改别的文件）、任何 `.db`、
`scripts/lp_rh_premium_recorder_v1_readonly.py`（注意：**recorder 不是 guard**，
另一条线正在改 recorder，别搞混）。
`tests/test_lp_rh_premium_guard_v1_readonly.py`（若存在）**只允许新增测试**。

## 验收标准

1. `generated_at` 领先 `now` 1 小时 → 返回 `INVALID`，不再是 `FRESH`。
2. 领先 3 秒（容差内）→ 仍是 `FRESH`（时钟微抖动不该误伤）。
3. 领先 10 秒（超容差）→ `INVALID`。
4. **防回归**：正常的正龄用例（0 秒、30 秒、59 秒、61 秒、3600 秒）
   行为与修改前完全一致。这条必须有。
5. `generated_at is None` → 仍是 `("UNKNOWN", -1)`（原行为不变）。
   注意 `-1` 这个哨兵值与新的负龄语义会撞车，
   **确保二者不会混淆**，并在测试里断言这一点。
6. `/root/lp-bot/.venv/bin/python -m pytest tests/ -k premium -q -p no:cacheprovider`
   全绿，原有测试全部仍在。

## 交付格式（只读沙箱）

```
===FILE:scripts/lp_rh_premium_guard_v1_readonly.py===
===FILE:<该模块真实的测试文件路径>===
===END===
```

先 `ls tests/ | grep -i premium` 确认真实测试文件名再动笔。
标记独占一行、一字不差，内容不要用代码围栏包裹。
