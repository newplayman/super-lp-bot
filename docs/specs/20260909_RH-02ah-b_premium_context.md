# RH-02ah-b：premium_recorder 的全局 Decimal 精度污染（RH-02ah 的续包）

## 现状（主脑已实测，不要重新调研）

RH-02ah 被推理网关 502 打断，三个目标文件里**已完成两个**：

| 文件 | 状态 |
|---|---|
| `scripts/lp_rh_exit_depth_v1_readonly.py` | **已完成**，`getcontext().prec = 80` 已删，6 处改用 `localcontext()` |
| `scripts/lp_rh_organic_recorder_v1_readonly.py` | **已完成**，1 处改用 `localcontext()` |
| `scripts/lp_rh_premium_recorder_v1_readonly.py` | **未开始**，第 35 行仍是 `getcontext().prec = 60` |

**本包只做最后这一个文件。前两个已经改好了，一个字都不要动。**

## 问题

`scripts/lp_rh_premium_recorder_v1_readonly.py:32,35`：

```python
from decimal import Decimal, getcontext
...
getcontext().prec = 60
```

**导入即改全局精度**（实测：导入前 28，导入后 60）。任何 import 到它的测试
都会在一个被改过的全局上下文里跑，于是「单独跑绿、全量跑红」。

## 你要做的

照抄前两个文件已经验证过的改法：

1. `from decimal import Decimal, getcontext` → `from decimal import Decimal, localcontext`
2. 删掉模块级的 `getcontext().prec = 60`
3. 找出该模块里**真正需要高精度的计算块**，用
   ```python
   with localcontext() as ctx:
       ctx.prec = 60
       ...计算...
   ```
   包住。**在 `with` 块内部把结果 `+x` 一下或直接 return**，
   确保结果在退出上下文前已经按 60 位定型
   （前两个文件就是这么做的，可以 `sed -n '110,125p' scripts/lp_rh_exit_depth_v1_readonly.py` 参考）。
4. 判断哪些块需要：凡是涉及 `sqrt_price` 平方、大整数相除、
   `10**decimals` 缩放、bps 换算的，都要包；纯加减和比较不需要。

**只改这一个文件。** 不许动 `exit_depth`、`organic_recorder`、
任何测试文件、任何其它 `scripts/`、任何 `.db`、`pool_meta.json`。

## 验收标准

1. 改完后 `grep -n 'getcontext' scripts/lp_rh_premium_recorder_v1_readonly.py` **无输出**。
2. 导入不再污染全局，用这条实测并把输出贴进报告：
   ```bash
   /root/lp-bot/.venv/bin/python -c "
   from decimal import getcontext
   print('before', getcontext().prec)
   import sys; sys.path.insert(0,'/opt/lpbot/lp-bot-v3-origin-check')
   import scripts.lp_rh_premium_recorder_v1_readonly
   print('after ', getcontext().prec)"
   ```
   **两行必须都是 28。**
3. `/root/lp-bot/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -5`
   贴出原样尾部。**期望：0 failed**（三个污染源全清后，
   那批「靠污染才绿」的 Decimal 测试应该回到默认精度下也能过；
   若仍有红，把失败的测试名原样列出来，**不要去改测试来让它绿**，
   那属于主脑判读范围）。
4. `git status --short | grep -v '^??'` 只应出现三行 ` M `：
   exit_depth、organic_recorder（前一包的产物，你没动）、premium_recorder（你改的）。

## 纪律（违反即退回）

- **不要执行任何 git 命令**（不 add、不 commit、不 stash、不 checkout）。
- 单次 Write/Edit ≤ 150 行或 6000 字符。
- 不要整读超过 300 行的文件，用 `sed -n 'a,bp'`。
- 不要重启任何 daemon / 录制器，不要动 crontab，不要发真实网络请求。
- 命令输出只贴尾部。
