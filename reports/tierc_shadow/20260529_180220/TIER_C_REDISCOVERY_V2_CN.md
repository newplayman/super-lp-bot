# Tier C Rediscovery V2

- previous_batch_status: `REJECTED`
- scanned_candidates_from_base_tierc_discovery: `15`
- MICRO_CANDIDATE_RESEARCH_ONLY: `0`
- SHADOW_ONLY: `1`
- WATCH: `7`
- REJECT: `7`

| pool_id | source_verdict | v2_research_verdict | fee_apr_estimate | volume_to_tvl | tvl_usd | vol24h_usd | risk_flags | why_kept_or_rejected |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf` | WATCH | REJECT | 16.5915538943245345 | 15.1521040130817746 | 29294.6034 | 443874.877738779 | market_quality_incomplete | v1_batch_reject_freeze |
| `0xc200f21efe67c7f41b81a854c26f9cda80593065` | WATCH | SHADOW_ONLY | 14.9780999204263485 | 5.8622700275641218 | 238543.2792 | 1398405.11593102 | market_quality_incomplete | raw_metrics_promising_but_market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0x659be70647b0f63217d60e077f4417b1ecc65064` | WATCH | WATCH | 5.495262002747164 | 1.5055512336293618 | 561712.8146 | 845687.420966451 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0xe8f16fbf4eafec04bcf0c06d768e7ba325f9d6de` | WATCH | WATCH | 3.965825399492376 | 3.6217583557008137 | 271596.5645 | 983657.12685751 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa` | WATCH | REJECT | 3.3741654885263015 | 3.0814296698870434 | 983099.0953 | 3029350.72069653 | market_quality_incomplete | v1_batch_reject_freeze |
| `0x82dbe18346a8656dbb5e76f74bf3ae279cc16b29` | WATCH | REJECT | 1.2977876459362995 | 7.1111651832126381 | 418551.8985 | 2976391.68798075 | market_quality_incomplete | v1_batch_reject_freeze |
| `0x0ba69825c4c033e72309f6ac0bde0023b15cc97c` | WATCH | WATCH | 1.153937972008756 | 6.3229477918287956 | 351877.0707 | 2224900.34717775 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830` | WATCH | REJECT | 0.8830335902874225 | 4.8385402207530577 | 249462.728 | 1207035.44300678 | market_quality_incomplete | v1_batch_reject_freeze |
| `0x9c087eb773291e50cf6c6a90ef0f4500e349b903` | WATCH | WATCH | 0.684399889394676 | 3.750136380244855 | 511305.4839 | 1917465.29659209 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0x20cb8f872ae894f7c9e32e621c186e5afce82fd0` | WATCH | WATCH | 0.626077524276804 | 3.4305617768591356 | 211038.167 | 723979.469168615 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0x3f9b863ef4b295d6ba370215bcca3785fcc44f44` | WATCH | WATCH | 0.376612404410022 | 2.0636296132055069 | 1767130.3138 | 3646702.44595082 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0xe640781d47992636fe7dd4822f2cdf6cb7d5e331f346bc58776a577ecd493fea` | WATCH | WATCH | 0.2548690590302045 | 6.9827139460326605 | 445629.1091 | 3111700.59487068 | market_quality_incomplete | market_quality_incomplete;trader_counts_missing;buyer_seller_missing |
| `0x3c4384f3664b37a3cb5a5cb3452b4b4a3aa1256f` | REJECT | REJECT | 3.004765760252394 | 3.292893983838252 | 1040851.7095 | 3427414.33228031 | known_negative_check | known_negative_check |
| `0x263dd54f58cedff35c85a98a61fda06f3bba55a567de33fe9f884d851652e37a` | REJECT | REJECT | 2.2824711220592295 | 15.6333638497208219 | 61526.135 | 961860.454722043 | native_zero_token | native_zero_token |
| `0xdc5a40b5be693afb1864c558da73e7d51b70579e53689cb3a41f85e6cdd6a7f6` | REJECT | REJECT | 0.2741060019463795 | 7.5097534779827635 | 35748.4759 | 268462.241222608 | native_zero_token | native_zero_token |

说明：V1 已 reject 的 4 个池默认不再进入 MICRO。当前扫描里未出现可直接升为 MICRO 的新池。
