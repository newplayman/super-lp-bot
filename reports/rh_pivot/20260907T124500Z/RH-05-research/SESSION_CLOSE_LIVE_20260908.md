# 首次实盘观测收盘转换，并由此挖出两个阻塞项（2026-09-08 20:1x UTC）

## 1. 转换本身：模块在实盘上判对了

美股 RTH 于 20:00 UTC（16:00 ET）收盘。溢价录制器的样本穿过了这个时刻，
`classify_session` 的判定：

| UTC | ET | session |
|---|---|---|
| 19:51:27 | 15:51:27 | `RTH` |
| **20:00:07** | **16:00:07** | **`POSTMARKET`** |
| 20:09:12 | 16:09:12 | `POSTMARKET` |

日历版本 `nyse-2026-v1`，`is_early_close: False`。**这是 T14–T16 的一次实盘验证**，
此前只有合成测试。

## 2. 推翻我自己的一个假设：收盘后参考价**不停更**

我在多份报告里写过「美股收盘后参考价停更而链价继续交易，溢价行为可能完全不同」。
实测：`POSTMARKET` 期间 SPY / QQQ / NVDA / GLD 四个标的的 `reference_mid` 与
`generatedAt` **每个采样点都在变**，报价龄稳定在 16–19 秒，与 RTH 期间没有区别。

溢价也没有在收盘瞬间跳变：

| 标的 | 19:51 (RTH) | 20:00 (收盘) | 20:09 (盘后) |
|---|---:|---:|---:|
| SPY | 22.95 | 22.23 | 26.37 |
| QQQ | 4.13 | −0.76 | 4.28 |
| NVDA | 8.56 | 10.10 | 1.18 |
| GLD | 68.79 | 71.56 | 72.78 |

**「收盘后参考价停更」这个担心不成立，至少在 POSTMARKET 时段不成立。**
仍未观测的是真正的 `OVERNIGHT`（盘后时段结束之后）与周末。

另注：GLD 的溢价从今天早些时候的约 36 bps 漂到了 69–73 bps，是六个标的里漂移最大的。

## 3. 阻塞项一：没有链上 oracle，STOCK **在 RTH 也永远开不了仓**

顺手验了开仓闸，发现它拒绝的理由有两个，其中一个是意料之外的：

```
session = POSTMARKET
health flags = ['ORACLE_STALE']
allows_new_position = False
```

`ORACLE_STALE` 从何而来？`evaluate_health` 在 `oracle_updated_at is None` 时就置这个 flag。
而**本项目今天已实测确认：RH 链的股票代币不引用任何链上价格源**
（见 `REFERENCE_PRICE_AND_PREMIUM_20260908.md` §1）。于是 `oracle_updated_at` 恒为 `None`。

在 RTH 时刻做对照实验：

| 情形 | flags | 可开仓 |
|---|---|---|
| **无链上 oracle（RH 链真实情况）** | `['ORACLE_STALE']` | **False** |
| 有 oracle 且新鲜 | `[]` | True |
| 有 oracle 但陈旧 | `['ORACLE_STALE']` | False |

**结论：在当前健康逻辑下，STOCK 桶永远无法开仓，与时段无关。**
这不是模块写错，是模块的假设（存在 oracle）与这条链的现实（不存在）不匹配。

而且「oracle 不存在」与「oracle 陈旧」被压成了同一个 flag。按本项目自己的纪律
（`STOCK_TOKEN_ABI_DISCOVERY` §1：「读取失败标 UNKNOWN，不当 false」），
**缺失与陈旧必须可区分**，否则读者无法判断这是暂时性问题还是结构性问题。

## 4. 阻塞项二：`stale_reason` 在无 oracle 时**直接崩溃**

```python
def stale_reason(session, oracle_age_secs, heartbeat_secs):
    if session != "RTH":
        return "EXPECTED_SESSION_CLOSED"
    if oracle_age_secs > heartbeat_secs:      # oracle_age_secs 为 None 时 TypeError
```

`TypeError: '>' not supported between instances of 'NoneType' and 'int'`。

可达性：`scripts/lp_rh_stock_reference_v1_readonly.py:125` 直接转调它（T23 路径），
而 RH 链上 `oracle_age_secs` **每次都是 `None`**。现有测试只覆盖了三个非 `None` 情形
（`tests/test_lp_rh_market_session_v1_readonly.py:95`），**崩溃路径无测试**。

## 5. 处置

两项已写成 `docs/specs/20260908_RH-02e_oracle_absent_semantics.md`：
新增 `ORACLE_UNAVAILABLE` 与 `ORACLE_STALE` 区分开，`stale_reason` 不再崩溃。

**仍然 fail-closed**——修完 STOCK 依旧开不了仓。但拒绝的理由会变成一个准确、显式、
可被用户看见的结论（「这条链没有链上价格源，是否接受用 REST `generatedAt` 作为
新鲜度依据，是一个需要拍板的政策决定」），而不是藏在一个用错了的 flag 名字里。
