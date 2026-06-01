# BSC amountIn raw conversion fix audit

- 稳定币输入使用 1 USD anchor。
- WBNB 输入必须先从 slot0 推导 WBNB/USD anchor，再换算为 raw。
- 其他非稳定币若缺 anchor，则 amountInRaw 标记不可用。
- audited_rows: `80`
