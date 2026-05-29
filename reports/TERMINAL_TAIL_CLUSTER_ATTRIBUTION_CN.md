# Terminal Tail Cluster Attribution

- total_samples = 12275
- negative_samples = 3847
- <= -1% = 2712
- <= -2% = 2712
- <= -5% = 0
- <= -10% = 0
- top_1pct_loss_share = 0.052892
- top_5pct_loss_share = 0.261749
- hhi_position = 0.294844
- hhi_pool = 0.303993

## Loss Contribution by Pool

| pool_id | loss_usd |
| --- | --- |
| 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 7398.449884 |
| 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 5827.785766 |
| 0x6c561b446416e1a00e8e93e221854d6ea4171372 | 3983.431197 |
| 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | 1548.494579 |

## Loss Contribution by Position

| position_id | loss_usd |
| --- | --- |
| shadow-pos-c5e8f94d64e82415136312e3 | 7174.082307 |
| shadow-pos-842896745e4337f71da620a9 | 5827.785766 |
| shadow-pos-b2b74e0686d4ef35496581ed | 3983.431197 |
| shadow-pos-2b1c5c39798221de81b22bb5 | 1548.494579 |
| shadow-pos-bad539974a504c8a7456e535 | 224.367577 |

## Loss Contribution by Exit Reason

| exit_reason | loss_usd |
| --- | --- |
| closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | 7174.082307 |
| closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | 5827.785766 |
| closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | 3983.431197 |
| closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | 1548.494579 |
| closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | 224.367577 |

## Loss Contribution by Exit Action

| exit_action | loss_usd |
| --- | --- |
| shadow_close | 18758.161426 |

## Excluding Worst Positions

| scenario | median | p10 | p5 | pct_signal |
| --- | --- | --- | --- | --- |
| exclude top 1 positions | 0.008347 | -2.370946 | -2.370946 | better |
| exclude top 3 positions | 0.034862 | -0.019768 | -0.019768 | worse |
| exclude top 5 positions | 0.271324 | 0.000779 | 0.000064 | better |

## Excluding Worst Pools

| scenario | median | p10 | p5 | pct_signal |
| --- | --- | --- | --- | --- |
| exclude top 1 pools | 0.008347 | -2.370946 | -2.370946 | better |
| exclude top 3 pools | 0.655024 | 0.000064 | -2.521978 | better |
