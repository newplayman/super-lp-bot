# Decimals Join Fix Audit

- mode: read-only repaired_v2 materialization

| Metric | Value |
| --- | ---: |
| before_join_success_count | 0 |
| after_join_success_count | 1 |
| before_token_decimals_missing | 10847 |
| after_token_decimals_missing | 0 |

## Token Status

| Token | rpc_decimals_ok | scanner_token_matches_pool | before_metadata_join | after_metadata_join_v2 | affected_selected_samples | affected_top20_samples |
| --- | --- | --- | --- | --- | ---: | ---: |
| DUAL | yes | no | no | no | 0 | 0 |
| PLAY | yes | no | no | no | 0 | 0 |
| USAD | yes | yes | no | yes | 10935 | 0 |
