# TAIL_RISK_AFTER_INVALID_REASON_FIX_CN

- `6h` clean_completed=42 median=0.116026221800985 p10=0.0214157416986751 p5=7.13323784538034e-05 p1=-3.79689268305334 negative_tail_status=WARN terminal_before_target_count=25 counterfactual_only_count=0
- `12h` clean_completed=40 median=0.0530412217709397 p10=-7.49662390050808 p5=-7.73250653575358 p1=-8.21804898736709 negative_tail_status=FAIL terminal_before_target_count=26 counterfactual_only_count=0
- `24h` clean_completed=8 median=0.0890857439030555 p10=0.00794336877659418 p5=0.00794336877659418 p1=0.00794336877659418 negative_tail_status=INSUFFICIENT terminal_before_target_count=57 counterfactual_only_count=0

- clean proof tail 仍然 12h FAIL。
- 24h 仍然 insufficient。
- classification fix 不改变策略结论。
- edge_proven: no
