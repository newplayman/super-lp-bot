# Terminal Clean SQL Diagnostic

- source: `shadow_outcome_labels_repaired_terminal_v1`

## Field Presence

| field | exists | type |
| --- | --- | --- |
| horizon | yes | text |
| outcome_type | yes | text |
| original_mark_source | yes | text |
| invalid_reason | yes | text |
| entry_value_source | yes | text |
| entry_value_confidence | yes | text |
| net_pnl_pct | yes | numeric |
| terminal_value_usd | yes | numeric |
| repair_version | no | N/A |
| selected | yes | boolean |
| score_total | yes | double precision |

## Full Column Listing

| ordinal | column_name | data_type |
| --- | --- | --- |
| 1 | id | text |
| 2 | decision_trace_id | text |
| 3 | position_id | text |
| 4 | horizon | text |
| 5 | tick_time | bigint |
| 6 | target_time | bigint |
| 7 | outcome_time | bigint |
| 8 | outcome_type | text |
| 9 | entry_value_usd | numeric |
| 10 | terminal_value_usd | numeric |
| 11 | future_value_usd | numeric |
| 12 | fee_usd | numeric |
| 13 | gas_usd | numeric |
| 14 | net_pnl_usd | numeric |
| 15 | net_pnl_pct | numeric |
| 16 | outcome_confidence | text |
| 17 | invalid_reason | text |
| 18 | valid_entry_strict | boolean |
| 19 | label | text |
| 20 | score_total | double precision |
| 21 | selected | boolean |
| 22 | intent_open | boolean |
| 23 | entry_value_source | text |
| 24 | entry_value_confidence | text |
| 25 | metadata_source | text |
| 26 | price_source | text |
| 27 | position_id_source | text |
| 28 | position_id_confidence | text |
| 29 | original_mark_source | text |
| 30 | root_cause_category | text |
| 31 | position_status_at_target | text |
| 32 | exit_reason | text |
| 33 | exit_action | text |
| 34 | exit_decision_time | bigint |
| 35 | exit_action_time | bigint |
| 36 | created_at | bigint |
| 37 | updated_at | bigint |

## Explicit Horizon Matrix

| horizon | total_rows | terminal_total | net_pnl_castable | terminal_value_castable | terminal_value_gt_zero | excl_zero_bug | excl_entry_untrusted | trusted_entry | excl_pool_mark_only | final_clean | blocking_filter | likely_reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 6h | 26275 | 5683 | 5683 | 5683 | 5656 | 5683 | 5638 | 5638 | 0 | 0 | exclude pool_mark_only | all terminal_exit_mark rows use original_mark_source=pool_mark_only |
| 24h | 24485 | 14047 | 14047 | 14047 | 14020 | 14047 | 12302 | 12302 | 0 | 0 | exclude pool_mark_only | all terminal_exit_mark rows use original_mark_source=pool_mark_only |

## Outcome Type Breakdown

| horizon | value | count |
| --- | --- | ---: |
| 24h | future_position_mark | 10354 |
| 24h | pool_mark_only | 84 |
| 24h | terminal_exit_mark | 14047 |
| 6h | future_position_mark | 20508 |
| 6h | pool_mark_only | 84 |
| 6h | terminal_exit_mark | 5683 |

## Repair Version Breakdown

| horizon | value | count |
| --- | --- | ---: |
| 24h | FIELD_MISSING | 24485 |
| 6h | FIELD_MISSING | 26275 |

## Mark Source Breakdown

| horizon | value | count |
| --- | --- | ---: |
| 24h | pool_mark_only | 14047 |
| 6h | pool_mark_only | 5683 |

## Invalid Reason Breakdown

| horizon | value | count |
| --- | --- | ---: |
| 24h |  | 12302 |
| 24h | entry_untrusted | 1745 |
| 6h |  | 5638 |
| 6h | entry_untrusted | 45 |

## Sample Terminal Rows

| decision_trace_id | position_id | horizon | outcome_type | mark_source | invalid_reason | entry_value_source | entry_value_confidence | terminal_value_usd | net_pnl_pct | repair_version | selected | score_total |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: |
| shadow-trace-000aeeb6850fcafd958bfb26 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | FIELD_MISSING | true | 63.8872477397611 |
| shadow-trace-000ea85f6e142f0ffdfb4df8 | shadow-pos-ec687b2aceeb808a1f6c75ac | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 1078.3949158518813575153328 | 7.839492 | FIELD_MISSING | true | 76.2684787898588 |
| shadow-trace-0010f570a3a888ffaa94e03b | shadow-pos-ed4a00d22f941ea02c4a9abb | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 202.4709991084237309256025 | 1.235500 | FIELD_MISSING | true | 62.6994995988821 |
| shadow-trace-0012eba3083d0b3000693619 | shadow-pos-b2b74e0686d4ef35496581ed | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 195.54426040569215024017376853162644427464483 | -2.227870 | FIELD_MISSING | true | 64.3818262633823 |
| shadow-trace-0018c31270d6f4d5ed37eece | shadow-pos-842896745e4337f71da620a9 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | FIELD_MISSING | true | 61.04897073146 |
| shadow-trace-0019b33c83aacd0b34b8e062 | shadow-pos-e2deacabdd6dcb7bc764a7bd | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.00155771679765097451969049957880779890912 | 0.000779 | FIELD_MISSING | true | 70.078502782292 |
| shadow-trace-00201f717d804d3ae83aa5af | shadow-pos-e2deacabdd6dcb7bc764a7bd | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.00155771679765097451969049957880779890912 | 0.000779 | FIELD_MISSING | true | 70.0786708702752 |
| shadow-trace-0021e8d9f0b0ff53cc95157a | shadow-pos-7f17b03d5f6152b6f693864d | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 201.310047334774738675677378049854819189 | 0.655024 | FIELD_MISSING | true | 62.8070234314438 |
| shadow-trace-0021e8d9f0b0ff53cc95157a | shadow-pos-7f17b03d5f6152b6f693864d | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 201.310047334774738675677378049854819189 | 0.655024 | FIELD_MISSING | true | 62.8070234314438 |
| shadow-trace-0023b358d3817ac84e5867ba | shadow-pos-842896745e4337f71da620a9 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | FIELD_MISSING | true | 63.637800150403 |
| shadow-trace-0024625a1136f4c417eab122 | shadow-pos-bad539974a504c8a7456e535 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | FIELD_MISSING | true | 75.5537360150373 |
| shadow-trace-0024625a1136f4c417eab122 | shadow-pos-bad539974a504c8a7456e535 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | FIELD_MISSING | true | 75.5537360150373 |
| shadow-trace-002bca6cba6a1f85b53234a6 | shadow-pos-e578fab5031843ede06449c2 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-002bca6cba6a1f85b53234a6 | shadow-pos-e578fab5031843ede06449c2 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-003220636370534ce0fb4223 | shadow-pos-91d83562aa038c689fc52a49 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-003220636370534ce0fb4223 | shadow-pos-91d83562aa038c689fc52a49 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-00334fe5a448a012156739f7 | shadow-pos-06eb7de3f0c56598add9777c | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 1002.71324162081500311290539375 | 0.271324 | FIELD_MISSING | true | 75.9277339536427 |
| shadow-trace-00338eeded47df87da530c06 | shadow-pos-f823ae9a69be0b66cb778ba8 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 205.26947305929007909953909920977940952 | 2.634737 | FIELD_MISSING | true | 71.687525841245 |
| shadow-trace-0034f37ed0842424c701fbc1 | shadow-pos-824c6f5ed8b582da1b0004a6 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 202.8612547392757147363574715781875827788 | 1.430627 | FIELD_MISSING | true | 67.8351565616669 |
| shadow-trace-003668dbae16fdae7219ce53 | shadow-pos-842896745e4337f71da620a9 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 195.258107594601557710014120366637939482135131 | -2.370946 | FIELD_MISSING | true | 63.637800150403 |
| shadow-trace-003860452bef2b1cf278b077 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | FIELD_MISSING | true | 63.8872477397611 |
| shadow-trace-00395f8fa9dc29efd00e2b75 | shadow-pos-257085443f2329f36ad3ad97 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.000061600700951719164958581535531233302462336 | 0.000031 | FIELD_MISSING | true | 70.0984322116561 |
| shadow-trace-00395f8fa9dc29efd00e2b75 | shadow-pos-257085443f2329f36ad3ad97 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.000061600700951719164958581535531233302462336 | 0.000031 | FIELD_MISSING | true | 70.0984322116561 |
| shadow-trace-003e0f6e8feffc6a88050ec1 | shadow-pos-d242d4f81bdc2b874e602b7a | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.1399141867032522625545134299829920860224075 | 0.069957 | FIELD_MISSING | true | 63.4543664312185 |
| shadow-trace-004056ef2df7f4fba90bedea | shadow-pos-bad539974a504c8a7456e535 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | FIELD_MISSING | true | 76.3915201648917 |
| shadow-trace-004056ef2df7f4fba90bedea | shadow-pos-bad539974a504c8a7456e535 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 999.8023193156580539767040199405395613796 | -0.019768 | FIELD_MISSING | true | 76.3915201648917 |
| shadow-trace-00431bae7eb866d0ebf0a21c | shadow-pos-e578fab5031843ede06449c2 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-00431bae7eb866d0ebf0a21c | shadow-pos-e578fab5031843ede06449c2 | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.04247897911151923643830832023720962569982032 | 0.021239 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-00441f650cfb5a43ef1a4bc5 | shadow-pos-91d83562aa038c689fc52a49 | 24h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 200.01655526362844377551159556625339564409423144 | 0.008278 | FIELD_MISSING | true | 63.8989600338655 |
| shadow-trace-0004efbd51ab7d5067afe3b5 | shadow-pos-06eb7de3f0c56598add9777c | 6h | terminal_exit_mark | pool_mark_only |  | positions_amount_usd | high | 1002.71324162081500311290539375 | 0.271324 | FIELD_MISSING | true | 76.5006806595535 |
