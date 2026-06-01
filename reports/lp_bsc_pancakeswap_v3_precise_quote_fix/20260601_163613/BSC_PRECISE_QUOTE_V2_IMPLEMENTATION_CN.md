# BSC PancakeSwap V3 Precise Quote V2 实施

- script: `scripts/lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py`
- selected_abi_variant: `pancakeswap_v3_struct`
- uses quoterV2 staticcall first, fallback math only if staticcall fails.
- no wallet / no tx / no signature / no router submit.
