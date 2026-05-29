# V11 Fixed Horizon Hypothesis Spec

## Scope

这是新策略假设，不是当前策略。

## Primary Proof Unit

- position_lifecycle

## Fixed Horizons

- 6h
- 24h
- optional 12h

## Prohibitions

- 不使用 terminal exit 作为成功证明
- 不用 decision_trace-level 作为 primary proof
- 不做 canary

## OOS Sample Thresholds

- <30: insufficient
- 30-100: early
- 100-300: preliminary
- >=300: usable

## Research Goal

验证 fixed-horizon / no-terminal 的新假设是否在 fresh OOS position-lifecycle 样本中成立。
