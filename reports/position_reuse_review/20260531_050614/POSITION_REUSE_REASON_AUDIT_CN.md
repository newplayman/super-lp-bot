# POSITION_REUSE_REASON_AUDIT_CN

- top reuse reason: position_already_open count=36016

## 结论
- reuse 更像正常策略逻辑与已开仓位复用，不是单纯 trace 误标。
- 存在 high-score intents 走 reuse_existing，而不是新建独立 position。
- 报告层应拆分 open_new vs reuse_existing，不能把它们都视作等价 new sample。
