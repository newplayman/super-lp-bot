# Terminal Position Mark Source Audit

- source table: `shadow_outcome_labels_repaired_terminal_v1`
- current terminal value source in repaired table: implied by `original_mark_source`
- current terminal net_pnl source in repaired table: no dedicated source column; derived from repaired row values

## Base Counts

| horizon | terminal_exit_mark total |
| --- | ---: |
| 24h | 14047 |
| 6h | 5683 |

## Original Mark Source Distribution

| horizon | original_mark_source | count |
| --- | --- | ---: |
| 24h | pool_mark_only | 14047 |
| 6h | pool_mark_only | 5683 |

## Exit Reason Distribution

| horizon | exit_reason | count |
| --- | --- | ---: |
| 24h | closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | 1338 |
| 24h | closed after 3669m; final pnl +1.6684 USD (fees +1.6693, il -0.0009, price -0.5990%) | 1332 |
| 24h | closed after 3816m; final pnl +78.3949 USD (fees +78.4308, il -0.0359, price -1.6800%) | 1332 |
| 24h | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | 1242 |
| 24h | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | 1149 |
| 24h | closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | 900 |
| 24h | closed after 722m; final pnl +2.8613 USD (fees +2.8638, il -0.0026, price +1.0178%) | 707 |
| 24h | closed after 724m; final pnl +1.3100 USD (fees +1.3166, il -0.0066, price +1.6340%) | 705 |
| 24h | closed after 1309m; final pnl +5.2695 USD (fees +5.2712, il -0.0018, price +0.8454%) | 640 |
| 24h | closed after 720m; final pnl +0.0697 USD (fees +0.0700, il -0.0002, price +0.3140%) | 602 |
| 24h | closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | 513 |
| 24h | closed after 1086m; final pnl +1.6131 USD (fees +1.6144, il -0.0013, price +0.7165%) | 422 |
| 24h | closed after 720m; final pnl +2.4710 USD (fees +2.4725, il -0.0015, price +0.7700%) | 342 |
| 24h | closed after 720m; final pnl +2.7132 USD (fees +2.7207, il -0.0074, price +0.7750%) | 342 |
| 24h | closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | 319 |
| 24h | closed after 737m; final pnl -5.0440 USD (fees +1.3727, il -6.4166, price +6.7392%) | 314 |
| 24h | closed after 313m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0052%) | 312 |
| 24h | closed after 943m; final pnl -25.4400 USD (fees +3.3633, il -28.8033, price -5.6777%) | 282 |
| 24h | closed after 3138m; final pnl +0.0005 USD (fees +0.0006, il -0.0001, price -0.1650%) | 212 |
| 24h | closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | 123 |
| 24h | closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | 121 |
| 24h | closed after 121m; final pnl +0.0143 USD (fees +0.0147, il -0.0004, price +0.3950%) | 118 |
| 24h | closed after 121m; final pnl +0.4378 USD (fees +0.4379, il 0.0000, price +0.0244%) | 117 |
| 24h | closed after 120m; final pnl +0.0167 USD (fees +0.0168, il -0.0001, price +0.2292%) | 116 |
| 24h | closed after 120m; final pnl +0.0143 USD (fees +0.0147, il -0.0003, price +0.3678%) | 115 |
| 24h | closed after 190m; final pnl +0.6207 USD (fees +0.6207, il 0.0000, price +0.1069%) | 107 |
| 24h | closed after 189m; final pnl +0.0017 USD (fees +0.0017, il 0.0000, price -0.0053%) | 106 |
| 24h | closed after 752m; final pnl +0.0482 USD (fees +0.0487, il -0.0005, price +0.4455%) | 91 |
| 24h | closed after 26m; final pnl -4.9554 USD (fees 0.0000, il -4.9554, price -0.1660%) | 26 |
| 24h | closed after 1m; final pnl -4.6813 USD (fees 0.0000, il -4.6813, price -4.9200%) | 1 |

## Exit Action Distribution

| horizon | exit_action | count |
| --- | --- | ---: |
| 24h | shadow_close | 14046 |
| 24h | hold | 1 |
| 6h | shadow_close | 5682 |
| 6h | hold | 1 |

## Horizon Coverage Checks

| horizon | total | has shadow_exit_decision | has shadow_exit_action | has closed/near-exit position mark | has mark within exit window | has same-position mark before exit | has same-position mark after exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 24h | 14047 | 14047 | 14019 | 14047 | 14047 | 14047 | 0 |
| 6h | 5683 | 5683 | 5655 | 5683 | 5683 | 5683 | 0 |

## Top Positions

| horizon | position_id | count |
| --- | --- | ---: |
| 24h | shadow-pos-e2deacabdd6dcb7bc764a7bd | 1338 |
| 24h | shadow-pos-b56917c6282e10d8858782aa | 1332 |
| 24h | shadow-pos-ec687b2aceeb808a1f6c75ac | 1332 |
| 24h | shadow-pos-842896745e4337f71da620a9 | 1242 |
| 24h | shadow-pos-bad539974a504c8a7456e535 | 1149 |
| 24h | shadow-pos-b2b74e0686d4ef35496581ed | 900 |
| 24h | shadow-pos-824c6f5ed8b582da1b0004a6 | 707 |
| 24h | shadow-pos-7f17b03d5f6152b6f693864d | 705 |
| 24h | shadow-pos-f823ae9a69be0b66cb778ba8 | 640 |
| 24h | shadow-pos-833713bf8f5b4cb1b0c6bf63 | 602 |
| 24h | shadow-pos-d242d4f81bdc2b874e602b7a | 513 |
| 24h | shadow-pos-fbeaeba5f113d78d37c03530 | 422 |
| 24h | shadow-pos-06eb7de3f0c56598add9777c | 342 |
| 24h | shadow-pos-ed4a00d22f941ea02c4a9abb | 342 |
| 24h | shadow-pos-e578fab5031843ede06449c2 | 319 |
| 24h | shadow-pos-2b1c5c39798221de81b22bb5 | 314 |
| 24h | shadow-pos-7efaae8b9be88674cd389b29 | 312 |
| 24h | shadow-pos-c5e8f94d64e82415136312e3 | 282 |
| 24h | shadow-pos-68ad1af5798162ee842fb8a8 | 212 |
| 24h | shadow-pos-91d83562aa038c689fc52a49 | 123 |
| 24h | shadow-pos-257085443f2329f36ad3ad97 | 121 |
| 24h | shadow-pos-9878cd860310b5e6e2eb81b4 | 118 |
| 24h | shadow-pos-5bbfdd99de9f74905e0a31af | 117 |
| 24h | shadow-pos-aba9eb8396fcbb72b1b30ba8 | 116 |
| 24h | shadow-pos-20a722d61ae673d983db7ac4 | 115 |
| 24h | shadow-pos-77ddf211104f42ab55b922c6 | 107 |
| 24h | shadow-pos-87f89e33d611c5b37a05cada | 106 |
| 24h | shadow-pos-e342ff683ff9e03607817d1a | 91 |
| 24h | shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 26 |
| 24h | shadow-canary-live-pos-299da787e60301c7c2c61c0f | 1 |
| 24h | shadow-canary-live-pos-87fed0fef84d468c20911210 | 1 |
| 6h | shadow-pos-842896745e4337f71da620a9 | 360 |
| 6h | shadow-pos-b2b74e0686d4ef35496581ed | 359 |
| 6h | shadow-pos-06eb7de3f0c56598add9777c | 358 |
| 6h | shadow-pos-ed4a00d22f941ea02c4a9abb | 358 |
| 6h | shadow-pos-e2deacabdd6dcb7bc764a7bd | 355 |
| 6h | shadow-pos-bad539974a504c8a7456e535 | 353 |
| 6h | shadow-pos-824c6f5ed8b582da1b0004a6 | 349 |
| 6h | shadow-pos-7f17b03d5f6152b6f693864d | 343 |
| 6h | shadow-pos-b56917c6282e10d8858782aa | 343 |

## Top Pools

| horizon | pool_ref | count |
| --- | --- | ---: |
| 24h | UNKNOWN | 14047 |
| 6h | UNKNOWN | 5683 |

## Special Positions

| position_id | horizon | count | min terminal_value_usd | max terminal_value_usd | min net_pnl_pct | max net_pnl_pct |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shadow-canary-live-pos-299da787e60301c7c2c61c0f | 24h | 1 | 0 | 0 | -100.000000 | -100.000000 |
| shadow-canary-live-pos-299da787e60301c7c2c61c0f | 6h | 1 | 0 | 0 | -100.000000 | -100.000000 |
| shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 24h | 26 | 0 | 0 | -100.000000 | -100.000000 |
| shadow-canary-live-pos-36bbaf9a2860d133daa0e42a | 6h | 26 | 0 | 0 | -100.000000 | -100.000000 |

## Top Position Coverage

| position_id | pool_ref | horizon | count | exit_decision | exit_action | near_exit_mark | before_exit_mark | after_exit_mark |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| shadow-pos-b2b74e0686d4ef35496581ed | UNKNOWN | 24h | 900 | 900 | 900 | 900 | 900 | 0 |
| shadow-pos-824c6f5ed8b582da1b0004a6 | UNKNOWN | 24h | 707 | 707 | 707 | 707 | 707 | 0 |
| shadow-pos-7f17b03d5f6152b6f693864d | UNKNOWN | 24h | 705 | 705 | 705 | 705 | 705 | 0 |
| shadow-pos-f823ae9a69be0b66cb778ba8 | UNKNOWN | 24h | 640 | 640 | 640 | 640 | 640 | 0 |
| shadow-pos-833713bf8f5b4cb1b0c6bf63 | UNKNOWN | 24h | 602 | 602 | 602 | 602 | 602 | 0 |
| shadow-pos-d242d4f81bdc2b874e602b7a | UNKNOWN | 24h | 513 | 513 | 513 | 513 | 513 | 0 |
| shadow-pos-d242d4f81bdc2b874e602b7a | UNKNOWN | 6h | 43 | 43 | 43 | 43 | 43 | 0 |
| shadow-pos-842896745e4337f71da620a9 | UNKNOWN | 6h | 360 | 360 | 360 | 360 | 360 | 0 |
| shadow-pos-b2b74e0686d4ef35496581ed | UNKNOWN | 6h | 359 | 359 | 359 | 359 | 359 | 0 |
| shadow-pos-06eb7de3f0c56598add9777c | UNKNOWN | 6h | 358 | 358 | 358 | 358 | 358 | 0 |
| shadow-pos-ed4a00d22f941ea02c4a9abb | UNKNOWN | 6h | 358 | 358 | 358 | 358 | 358 | 0 |
| shadow-pos-e2deacabdd6dcb7bc764a7bd | UNKNOWN | 6h | 355 | 355 | 355 | 355 | 355 | 0 |
| shadow-pos-bad539974a504c8a7456e535 | UNKNOWN | 6h | 353 | 353 | 353 | 353 | 353 | 0 |
| shadow-pos-824c6f5ed8b582da1b0004a6 | UNKNOWN | 6h | 349 | 349 | 349 | 349 | 349 | 0 |
| shadow-pos-7f17b03d5f6152b6f693864d | UNKNOWN | 6h | 343 | 343 | 343 | 343 | 343 | 0 |
| shadow-pos-b56917c6282e10d8858782aa | UNKNOWN | 6h | 343 | 343 | 343 | 343 | 343 | 0 |
| shadow-pos-ec687b2aceeb808a1f6c75ac | UNKNOWN | 6h | 343 | 343 | 343 | 343 | 343 | 0 |
| shadow-pos-06eb7de3f0c56598add9777c | UNKNOWN | 24h | 342 | 342 | 342 | 342 | 342 | 0 |
| shadow-pos-ed4a00d22f941ea02c4a9abb | UNKNOWN | 24h | 342 | 342 | 342 | 342 | 342 | 0 |
| shadow-pos-e578fab5031843ede06449c2 | UNKNOWN | 24h | 319 | 319 | 319 | 319 | 319 | 0 |
| shadow-pos-e578fab5031843ede06449c2 | UNKNOWN | 6h | 319 | 319 | 319 | 319 | 319 | 0 |
| shadow-pos-833713bf8f5b4cb1b0c6bf63 | UNKNOWN | 6h | 313 | 313 | 313 | 313 | 313 | 0 |
| shadow-pos-7efaae8b9be88674cd389b29 | UNKNOWN | 24h | 312 | 312 | 312 | 312 | 312 | 0 |
| shadow-pos-7efaae8b9be88674cd389b29 | UNKNOWN | 6h | 312 | 312 | 312 | 312 | 312 | 0 |
| shadow-pos-f823ae9a69be0b66cb778ba8 | UNKNOWN | 6h | 2 | 2 | 2 | 2 | 2 | 0 |
| shadow-pos-e2deacabdd6dcb7bc764a7bd | UNKNOWN | 24h | 1338 | 1338 | 1338 | 1338 | 1338 | 0 |
| shadow-pos-b56917c6282e10d8858782aa | UNKNOWN | 24h | 1332 | 1332 | 1332 | 1332 | 1332 | 0 |
| shadow-pos-ec687b2aceeb808a1f6c75ac | UNKNOWN | 24h | 1332 | 1332 | 1332 | 1332 | 1332 | 0 |
| shadow-pos-842896745e4337f71da620a9 | UNKNOWN | 24h | 1242 | 1242 | 1242 | 1242 | 1242 | 0 |
| shadow-pos-bad539974a504c8a7456e535 | UNKNOWN | 24h | 1149 | 1149 | 1149 | 1149 | 1149 | 0 |

## Sample Terminal Rows

| decision_trace_id | position_id | horizon | pool_ref | exit_reason | exit_action | original_mark_source | entry_value_source | entry_value_confidence | terminal_value_usd | net_pnl_pct | has_exit_decision | has_exit_action | near_exit_mark | before_exit_mark | after_exit_mark |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| shadow-trace-0004efbd51ab7d5067afe3b5 | shadow-pos-06eb7de3f0c56598add9777c | 6h | UNKNOWN | closed after 720m; final pnl +2.7132 USD (fees +2.7207, il -0.0074, price +0.7750%) | shadow_close | pool_mark_only | positions_amount_usd | high | 1002.71324162081500311290539375 | 0.271324 | yes | yes | yes | yes | no |
| shadow-trace-000aeeb6850fcafd958bfb26 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | UNKNOWN | closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | yes | yes | yes | yes | no |
| shadow-trace-000ea85f6e142f0ffdfb4df8 | shadow-pos-ec687b2aceeb808a1f6c75ac | 24h | UNKNOWN | closed after 3816m; final pnl +78.3949 USD (fees +78.4308, il -0.0359, price -1.6800%) | shadow_close | pool_mark_only | positions_amount_usd | high | 1078.3949158518813575153328 | 7.839492 | yes | yes | yes | yes | no |
| shadow-trace-0010f570a3a888ffaa94e03b | shadow-pos-ed4a00d22f941ea02c4a9abb | 24h | UNKNOWN | closed after 720m; final pnl +2.4710 USD (fees +2.4725, il -0.0015, price +0.7700%) | shadow_close | pool_mark_only | positions_amount_usd | high | 202.4709991084237309256025 | 1.235500 | yes | yes | yes | yes | no |
| shadow-trace-0012eba3083d0b3000693619 | shadow-pos-b2b74e0686d4ef35496581ed | 24h | UNKNOWN | closed after 2678m; final pnl -4.4557 USD (fees +0.5263, il -4.9821, price -4.9200%) | shadow_close | pool_mark_only | positions_amount_usd | high | 195.54426040569215024017376853162644427464483 | -2.227870 | yes | yes | yes | yes | no |
| shadow-trace-0018c31270d6f4d5ed37eece | shadow-pos-842896745e4337f71da620a9 | 24h | UNKNOWN | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | shadow_close | pool_mark_only | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | yes | yes | yes | yes | no |
| shadow-trace-0019b33c83aacd0b34b8e062 | shadow-pos-e2deacabdd6dcb7bc764a7bd | 24h | UNKNOWN | closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.00155771679765097451969049957880779890912 | 0.000779 | yes | yes | yes | yes | no |
| shadow-trace-00201f717d804d3ae83aa5af | shadow-pos-e2deacabdd6dcb7bc764a7bd | 24h | UNKNOWN | closed after 3743m; final pnl +0.0016 USD (fees +0.0016, il 0.0000, price -0.0010%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.00155771679765097451969049957880779890912 | 0.000779 | yes | yes | yes | yes | no |
| shadow-trace-0021e8d9f0b0ff53cc95157a | shadow-pos-7f17b03d5f6152b6f693864d | 24h | UNKNOWN | closed after 724m; final pnl +1.3100 USD (fees +1.3166, il -0.0066, price +1.6340%) | shadow_close | pool_mark_only | positions_amount_usd | high | 201.310047334774738675677378049854819189 | 0.655024 | yes | yes | yes | yes | no |
| shadow-trace-0021e8d9f0b0ff53cc95157a | shadow-pos-7f17b03d5f6152b6f693864d | 6h | UNKNOWN | closed after 724m; final pnl +1.3100 USD (fees +1.3166, il -0.0066, price +1.6340%) | shadow_close | pool_mark_only | positions_amount_usd | high | 201.310047334774738675677378049854819189 | 0.655024 | yes | yes | yes | yes | no |
| shadow-trace-0023b358d3817ac84e5867ba | shadow-pos-842896745e4337f71da620a9 | 24h | UNKNOWN | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | shadow_close | pool_mark_only | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | yes | yes | yes | yes | no |
| shadow-trace-0024625a1136f4c417eab122 | shadow-pos-bad539974a504c8a7456e535 | 24h | UNKNOWN | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | pool_mark_only | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | yes | yes | yes | yes | no |
| shadow-trace-0024625a1136f4c417eab122 | shadow-pos-bad539974a504c8a7456e535 | 6h | UNKNOWN | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | pool_mark_only | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | yes | yes | yes | yes | no |
| shadow-trace-002bca6cba6a1f85b53234a6 | shadow-pos-e578fab5031843ede06449c2 | 24h | UNKNOWN | closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | yes | yes | yes | yes | no |
| shadow-trace-002bca6cba6a1f85b53234a6 | shadow-pos-e578fab5031843ede06449c2 | 6h | UNKNOWN | closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | yes | yes | yes | yes | no |
| shadow-trace-003220636370534ce0fb4223 | shadow-pos-91d83562aa038c689fc52a49 | 24h | UNKNOWN | closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | yes | yes | yes | yes | no |
| shadow-trace-003220636370534ce0fb4223 | shadow-pos-91d83562aa038c689fc52a49 | 6h | UNKNOWN | closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | yes | yes | yes | yes | no |
| shadow-trace-00334fe5a448a012156739f7 | shadow-pos-06eb7de3f0c56598add9777c | 6h | UNKNOWN | closed after 720m; final pnl +2.7132 USD (fees +2.7207, il -0.0074, price +0.7750%) | shadow_close | pool_mark_only | positions_amount_usd | high | 1002.71324162081500311290539375 | 0.271324 | yes | yes | yes | yes | no |
| shadow-trace-00338eeded47df87da530c06 | shadow-pos-f823ae9a69be0b66cb778ba8 | 24h | UNKNOWN | closed after 1309m; final pnl +5.2695 USD (fees +5.2712, il -0.0018, price +0.8454%) | shadow_close | pool_mark_only | positions_amount_usd | high | 205.26947305929007909953909920977940952 | 2.634737 | yes | yes | yes | yes | no |
| shadow-trace-0034f37ed0842424c701fbc1 | shadow-pos-824c6f5ed8b582da1b0004a6 | 24h | UNKNOWN | closed after 722m; final pnl +2.8613 USD (fees +2.8638, il -0.0026, price +1.0178%) | shadow_close | pool_mark_only | positions_amount_usd | high | 202.8612547392757147363574715781875827788 | 1.430627 | yes | yes | yes | yes | no |
| shadow-trace-003668dbae16fdae7219ce53 | shadow-pos-842896745e4337f71da620a9 | 24h | UNKNOWN | closed after 2940m; final pnl -4.7419 USD (fees +0.3838, il -5.1257, price -5.0600%) | shadow_close | pool_mark_only | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | yes | yes | yes | yes | no |
| shadow-trace-003860452bef2b1cf278b077 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | UNKNOWN | closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | yes | yes | yes | yes | no |
| shadow-trace-00395f8fa9dc29efd00e2b75 | shadow-pos-257085443f2329f36ad3ad97 | 24h | UNKNOWN | closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.000061600700951719164958581535531233302462336 | 0.000031 | yes | yes | yes | yes | no |
| shadow-trace-00395f8fa9dc29efd00e2b75 | shadow-pos-257085443f2329f36ad3ad97 | 6h | UNKNOWN | closed after 120m; final pnl +0.0001 USD (fees +0.0001, il 0.0000, price +0.0126%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.000061600700951719164958581535531233302462336 | 0.000031 | yes | yes | yes | yes | no |
| shadow-trace-003e0f6e8feffc6a88050ec1 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | UNKNOWN | closed after 1177m; final pnl +0.1399 USD (fees +0.1404, il -0.0005, price -0.4577%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | yes | yes | yes | yes | no |
| shadow-trace-004056ef2df7f4fba90bedea | shadow-pos-bad539974a504c8a7456e535 | 24h | UNKNOWN | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | pool_mark_only | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | yes | yes | yes | yes | no |
| shadow-trace-004056ef2df7f4fba90bedea | shadow-pos-bad539974a504c8a7456e535 | 6h | UNKNOWN | closed after 1175m; final pnl -0.1977 USD (fees +24.6220, il -24.8196, price -4.9023%) | shadow_close | pool_mark_only | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | yes | yes | yes | yes | no |
| shadow-trace-00431bae7eb866d0ebf0a21c | shadow-pos-e578fab5031843ede06449c2 | 24h | UNKNOWN | closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | yes | yes | yes | yes | no |
| shadow-trace-00431bae7eb866d0ebf0a21c | shadow-pos-e578fab5031843ede06449c2 | 6h | UNKNOWN | closed after 321m; final pnl +0.0425 USD (fees +0.0433, il -0.0009, price +0.5867%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | yes | yes | yes | yes | no |
| shadow-trace-00441f650cfb5a43ef1a4bc5 | shadow-pos-91d83562aa038c689fc52a49 | 24h | UNKNOWN | closed after 122m; final pnl +0.0166 USD (fees +0.0167, il -0.0001, price +0.2237%) | shadow_close | pool_mark_only | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | yes | yes | yes | yes | no |

## Source Judgment

- `terminal_exit_mark total` is non-zero, but `original_mark_source` is uniformly `pool_mark_only` in the repaired table.
- there is no dedicated `terminal_value_source` or `terminal_net_pnl_source` column in `shadow_outcome_labels_repaired_terminal_v1`; current source attribution is only inferable via `original_mark_source`.
- this means the current terminal-inclusive path cannot prove position-level terminal valuation.
