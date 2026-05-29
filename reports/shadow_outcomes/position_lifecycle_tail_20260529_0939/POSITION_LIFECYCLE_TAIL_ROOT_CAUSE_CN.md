# Position Lifecycle Tail Root Cause

Position-level proof only. Decision-trace rows are not used as the primary proof unit.

# Horizon Summary

| horizon | position_count | losing_position_count | p10 | p5 | p1 | <= -0.5% | <= -1% | <= -2% | <= -5% | <= -10% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 24h | 33 | 5 | -2.242177 | -2.454014 | -2.537614 | 4 | 4 | 4 | 0 | 0 |
| 6h | 35 | 6 | -2.356639 | -2.531888 | -3.408496 | 5 | 5 | 5 | 0 | 0 |

# Worst 20 Positions

| horizon | position_id | pool_id | token_pair | open_time | exit_time | holding_minutes | entry_value_usd | final_value_usd | net_pnl_pct | outcome_type | exit_reason | exit_action | score_open_decision | score_first_selected | score_max_before_open | score_median_before_open | decision_trace_count | terminal/future | root_cause |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 6h | shadow-pos-e342ff683ff9e03607817d1a | 0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | base:pancakeswap-v3-base:0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | 1779641197 | 1779686340 | 752 | 200 | 192.4062146338933105323499651241361774970409954 | -3.796893 | future_position_mark |  |  | 60.7983483109059 | 60.7983483109059 | 60.7983483109059 | 60.7983483109059 | 91 | future | UNKNOWN |
| 24h | shadow-pos-c5e8f94d64e82415136312e3 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 1779632243 | 1779688854 | 943 | 1000.0 | 974.5599918180734 | -2.5440008181926563 | terminal_exit_mark | closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | shadow_close | 76.3915201648917 | 76.3915201648917 | 76.3915201648917 | 76.3915201648917 | 282 | terminal | REAL_TERMINAL_LOSS |
| 6h | shadow-pos-c5e8f94d64e82415136312e3 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 1779632243 | 1779688854 | 943 | 1000.0 | 974.5599918180734 | -2.5440008181926563 | terminal_exit_mark | closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | shadow_close | 76.3915201648917 | 76.3915201648917 | 76.3915201648917 | 76.3915201648917 | 282 | terminal | REAL_TERMINAL_LOSS |
| 24h | shadow-pos-2b1c5c39798221de81b22bb5 | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | base:aerodrome-slipstream:0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | 1779533423 | 1779577682 | 737 | 200.0 | 194.9560437174863 | -2.5219781412568474 | terminal_exit_mark | closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | shadow_close | 60.1476644078684 | 60.1476644078684 | 60.1476644078684 | 60.1476644078684 | 314 | terminal | REAL_TERMINAL_LOSS |
| 6h | shadow-pos-2b1c5c39798221de81b22bb5 | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | base:aerodrome-slipstream:0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | 1779533423 | 1779577682 | 737 | 200.0 | 194.9560437174863 | -2.5219781412568474 | terminal_exit_mark | closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | shadow_close | 60.1476644078684 | 60.1476644078684 | 60.1476644078684 | 60.1476644078684 | 314 | terminal | REAL_TERMINAL_LOSS |
| 24h | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | base:pancakeswap-v3-base:0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 1779346211 | 1779522662 | 2940 | 200.0 | 195.25810759460157 | -2.370946202699221 | terminal_exit_mark | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | shadow_close | 62.1431613895643 | 62.1431613895643 | 62.1431613895643 | 62.1431613895643 | 2678 | terminal | REAL_TERMINAL_LOSS |
| 6h | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | base:pancakeswap-v3-base:0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 1779346211 | 1779522662 | 2940 | 200.0 | 195.25810759460157 | -2.370946202699221 | terminal_exit_mark | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | shadow_close | 62.1431613895643 | 62.1431613895643 | 62.1431613895643 | 62.1431613895643 | 2678 | terminal | REAL_TERMINAL_LOSS |
| 24h | shadow-pos-b2b74e0686d4ef35496581ed | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 1779362600 | 1779523303 | 2678 | 200.0 | 195.54426040569214 | -2.2278697971539247 | terminal_exit_mark | closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | shadow_close | 63.6712808409811 | 63.6712808409811 | 63.6712808409811 | 63.6712808409811 | 2028 | terminal | REAL_TERMINAL_LOSS |
| 6h | shadow-pos-b2b74e0686d4ef35496581ed | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 1779362600 | 1779523303 | 2678 | 200.0 | 195.54426040569214 | -2.2278697971539247 | terminal_exit_mark | closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | shadow_close | 63.6712808409811 | 63.6712808409811 | 63.6712808409811 | 63.6712808409811 | 2028 | terminal | REAL_TERMINAL_LOSS |
| 24h | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 1779561712 | 1779632239 | 1175 | 1000.0 | 999.8023193156581 | -0.019768068434194604 | terminal_exit_mark | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | 76.0533018504318 | 76.0533018504318 | 76.0533018504318 | 76.0533018504318 | 1149 | terminal | REAL_TERMINAL_LOSS |
| 6h | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 1779561712 | 1779632239 | 1175 | 1000.0 | 999.8023193156581 | -0.019768068434194604 | terminal_exit_mark | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | 76.0533018504318 | 76.0533018504318 | 76.0533018504318 | 76.0533018504318 | 1149 | terminal | REAL_TERMINAL_LOSS |
| 24h | shadow-pos-257085443f2329f36ad3ad97 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779568808 | 1779576063 | 120 | 200.0 | 200.00006160070095 | 0.00003080035047585958 | terminal_exit_mark | closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | shadow_close | 70.0984322116561 | 70.0984322116561 | 70.0984322116561 | 70.0984322116561 | 121 | terminal | UNKNOWN |
| 6h | shadow-pos-257085443f2329f36ad3ad97 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779568808 | 1779576063 | 120 | 200.0 | 200.00006160070095 | 0.00003080035047585958 | terminal_exit_mark | closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | shadow_close | 70.0984322116561 | 70.0984322116561 | 70.0984322116561 | 70.0984322116561 | 121 | terminal | UNKNOWN |
| 24h | shadow-pos-7efaae8b9be88674cd389b29 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779576119 | 1779594904 | 313 | 200.0 | 200.00012899101327 | 0.00006449550663820503 | terminal_exit_mark | closed after 313m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0052%) | shadow_close | 70.1212409497623 | 70.1212409497623 | 70.1212409497623 | 70.1212409497623 | 312 | terminal | TRACE_DUPLICATION_ARTIFACT |
| 6h | shadow-pos-7efaae8b9be88674cd389b29 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779576119 | 1779594904 | 313 | 200.0 | 200.00012899101327 | 0.00006449550663820503 | terminal_exit_mark | closed after 313m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0052%) | shadow_close | 70.1212409497623 | 70.1212409497623 | 70.1212409497623 | 70.1212409497623 | 312 | terminal | TRACE_DUPLICATION_ARTIFACT |
| 6h | shadow-canary-live-pos-87fed0fef84d468c20911210 | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 1779504100 | 1779505946 | 30 | 4.803986804856903 | 4.803990126371387 | 0.00006914079116248526 | terminal_exit_mark | hold: no current exit condition met | hold | 64.3818262633823 | 64.3818262633823 | 64.3818262633823 | 64.3818262633823 | 1 | terminal | UNKNOWN |
| 24h | shadow-canary-live-pos-87fed0fef84d468c20911210 | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 1779504100 | 1779505946 | 30 | 4.803986804856903 | 4.803990126371387 | 0.00006914079116248526 | terminal_exit_mark | hold: no current exit condition met | hold | 64.3818262633823 | 64.3818262633823 | 64.3818262633823 | 64.3818262633823 | 1 | terminal | UNKNOWN |
| 6h | shadow-pos-68ad1af5798162ee842fb8a8 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779594960 | 1779783244 | 3138 | 200 | 200.00014266475690265088966195255 | 0.000071 | future_position_mark |  |  | 70.1177584762113 | 70.1177584762113 | 70.1177584762113 | 70.1177584762113 | 1673 | future | TRACE_DUPLICATION_ARTIFACT |
| 24h | shadow-pos-68ad1af5798162ee842fb8a8 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779594960 | 1779783244 | 3138 | 200.0 | 200.00050084024528 | 0.0002504201226380587 | terminal_exit_mark | closed after 3138m; final pnl +0.0005 USD (fees +0.0006, il -0.0001, price -0.1650%) | shadow_close | 70.1177584762113 | 70.1177584762113 | 70.1177584762113 | 70.1177584762113 | 1226 | terminal | TRACE_DUPLICATION_ARTIFACT |
| 24h | shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 1779344120 | 1779568751 | 3743 | 200.0 | 200.00155771679766 | 0.0007788583988254873 | terminal_exit_mark | closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | shadow_close | 67.9458961036126 | 67.9458961036126 | 67.9458961036126 | 67.9458961036126 | 3479 | terminal | TRACE_DUPLICATION_ARTIFACT |

## 6h Worst 20 Pools

| pool_id | token_pair | position_count | losing_position_count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | --- | ---: | ---: | ---: | ---: |
| 0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | base:pancakeswap-v3-base:0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | 1 | 1 | -3.796893 | -3.796893 |
| 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 5 | 2 | 1.132549 | -2.544001 |
| 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | base:aerodrome-slipstream:0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | 3 | 1 | -0.602884 | -2.521978 |
| 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | base:pancakeswap-v3-base:0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 11 | 1 | -0.019944 | -2.370946 |
| 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 5 | 1 | -1.113900 | -2.227870 |
| 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 5 | 0 | 0.000358 | 0.000031 |
| 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | base:aerodrome-slipstream:0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 5 | 0 | 1.063698 | 0.108591 |

## 6h Worst Exit Reason

| exit_reason | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
|  | 7 | -0.495682 | -3.796893 |
| closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | 1 | -2.544001 | -2.544001 |
| closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | 1 | -2.521978 | -2.521978 |
| closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | 1 | -2.370946 | -2.370946 |
| closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | 1 | -2.227870 | -2.227870 |
| closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | 1 | -0.019768 | -0.019768 |
| closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | 1 | 0.000031 | 0.000031 |
| closed after 313m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0052%) | 1 | 0.000064 | 0.000064 |
| hold: no current exit condition met | 1 | 0.000069 | 0.000069 |
| closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | 1 | 0.000779 | 0.000779 |
| closed after 189m; final pnl +0.0017 USD (fees +0.0017, il 0.0000, price -0.0053%) | 1 | 0.000845 | 0.000845 |
| closed after 121m; final pnl +0.0143 USD (fees +0.0147, il -0.0004, price +0.3950%) | 1 | 0.007158 | 0.007158 |
| closed after 120m; final pnl +0.0143 USD (fees +0.0147, il -0.0003, price +0.3678%) | 1 | 0.007158 | 0.007158 |
| closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | 1 | 0.008278 | 0.008278 |
| closed after 120m; final pnl +0.0167 USD (fees +0.0168, il -0.0001, price +0.2292%) | 1 | 0.008347 | 0.008347 |
| closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | 1 | 0.021239 | 0.021239 |
| closed after 720m; final pnl +0.0697 USD (fees +0.0700, il -0.0002, price +0.3140%) | 1 | 0.034862 | 0.034862 |
| closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | 1 | 0.069957 | 0.069957 |
| closed after 121m; final pnl +0.4378 USD (fees +0.4379, il 0.0000, price +0.0244%) | 1 | 0.218925 | 0.218925 |
| closed after 720m; final pnl +2.7132 USD (fees +2.7207, il -0.0074, price +0.7750%) | 1 | 0.271324 | 0.271324 |

## 6h Worst Exit Action

| exit_action | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
|  | 7 | -0.495682 | -3.796893 |
| shadow_close | 27 | 0.236173 | -2.544001 |
| hold | 1 | 0.000069 | 0.000069 |

## 6h Worst Holding Bucket

| holding_bucket | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| 6-24h | 14 | -0.131176 | -3.796893 |
| 24h+ | 6 | 0.679287 | -2.370946 |
| 1-6h | 10 | 0.058238 | 0.000031 |
| <1h | 5 | 0.054330 | 0.000069 |

## 6h Worst Score Bucket

| score_bucket | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| 60-69 | 23 | -0.331024 | -3.796893 |
| 70-79 | 12 | 0.795898 | -2.544001 |

## 24h Worst 20 Pools

| pool_id | token_pair | position_count | losing_position_count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | --- | ---: | ---: | ---: | ---: |
| 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 4 | 2 | 1.386762 | -2.544001 |
| 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | base:aerodrome-slipstream:0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | 3 | 1 | -0.353463 | -2.521978 |
| 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | base:pancakeswap-v3-base:0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | 10 | 1 | -0.075952 | -2.370946 |
| 0x6c561b446416e1a00e8e93e221854d6ea4171372 | base:uniswap-v3-base:0x6c561b446416e1a00e8e93e221854d6ea4171372 | 5 | 1 | -1.113900 | -2.227870 |
| 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 5 | 0 | 0.000394 | 0.000031 |
| 0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | base:pancakeswap-v3-base:0xc211e1f853a898bd1302385ccde55f33a8c4b3f3 | 1 | 0 | 0.024095 | 0.024095 |
| 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | base:aerodrome-slipstream:0x4e962bb3889bf030368f56810a9c96b83cb3e778 | 5 | 0 | 1.408807 | 0.310337 |

## 24h Worst Exit Reason

| exit_reason | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | 1 | -2.544001 | -2.544001 |
| closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | 1 | -2.521978 | -2.521978 |
| closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | 1 | -2.370946 | -2.370946 |
| closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | 1 | -2.227870 | -2.227870 |
| closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | 1 | -0.019768 | -0.019768 |
| closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | 1 | 0.000031 | 0.000031 |
| closed after 313m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0052%) | 1 | 0.000064 | 0.000064 |
| hold: no current exit condition met | 1 | 0.000069 | 0.000069 |
| closed after 3138m; final pnl +0.0005 USD (fees +0.0006, il -0.0001, price -0.1650%) | 1 | 0.000250 | 0.000250 |
| closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | 1 | 0.000779 | 0.000779 |
| closed after 189m; final pnl +0.0017 USD (fees +0.0017, il 0.0000, price -0.0053%) | 1 | 0.000845 | 0.000845 |
| closed after 121m; final pnl +0.0143 USD (fees +0.0147, il -0.0004, price +0.3950%) | 1 | 0.007158 | 0.007158 |
| closed after 120m; final pnl +0.0143 USD (fees +0.0147, il -0.0003, price +0.3678%) | 1 | 0.007158 | 0.007158 |
| closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | 1 | 0.008278 | 0.008278 |
| closed after 120m; final pnl +0.0167 USD (fees +0.0168, il -0.0001, price +0.2292%) | 1 | 0.008347 | 0.008347 |
| closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | 1 | 0.021239 | 0.021239 |
| closed after 752m; final pnl +0.0482 USD (fees +0.0487, il -0.0005, price +0.4455%) | 1 | 0.024095 | 0.024095 |
| closed after 720m; final pnl +0.0697 USD (fees +0.0700, il -0.0002, price +0.3140%) | 1 | 0.034862 | 0.034862 |
| closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | 1 | 0.069957 | 0.069957 |
| closed after 121m; final pnl +0.4378 USD (fees +0.4379, il 0.0000, price +0.0244%) | 1 | 0.218925 | 0.218925 |

## 24h Worst Exit Action

| exit_action | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| shadow_close | 30 | 0.240544 | -2.544001 |
| hold | 1 | 0.000069 | 0.000069 |
|  | 2 | 1.834137 | 1.834137 |

## 24h Worst Holding Bucket

| holding_bucket | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| 6-24h | 12 | 0.173079 | -2.544001 |
| 24h+ | 6 | 0.679317 | -2.370946 |
| 1-6h | 10 | 0.058238 | 0.000031 |
| <1h | 5 | 0.917103 | 0.000069 |

## 24h Worst Score Bucket

| score_bucket | count | avg_net_pnl_pct | worst_net_pnl_pct |
| --- | ---: | ---: | ---: |
| 70-79 | 11 | 1.014618 | -2.544001 |
| 60-69 | 22 | -0.136388 | -2.521978 |

