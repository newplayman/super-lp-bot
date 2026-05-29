# TIER_C_ONCHAIN_LOGS_FALLBACK

- rpc_url: `https://mainnet.base.org`
- supported_count: 5
- success_pool_count: 1
- note: trader concentration uses on-chain tx sender as read-only trader proxy; volume share is tx-share proxy within each pool/window.

## 0xc200f21efe67c7f41b81a854c26f9cda80593065
- 1h: protocol=uniswap_v3_like logs=423 unique=n/a top1=n/a top5=n/a dq=missing failure=tx_sender_unavailable
- 6h: protocol=uniswap_v3_like logs=1578 unique=n/a top1=n/a top5=n/a dq=missing failure=tx_sender_unavailable
- 24h: protocol=uniswap_v3_like logs=6105 unique=n/a top1=n/a top5=n/a dq=missing failure=tx_sender_unavailable

## 0xe8f16fbf4eafec04bcf0c06d768e7ba325f9d6de
- 1h: protocol=uniswap_v3_like logs=938 unique=1 top1=100.00 top5=100.00 dq=ok failure=none
- 6h: protocol=uniswap_v3_like logs=4651 unique=5 top1=20.00 top5=100.00 dq=ok failure=none
- 24h: protocol=uniswap_v3_like logs=8610 unique=9 top1=11.11 top5=55.56 dq=ok failure=none

## 0x0ba69825c4c033e72309f6ac0bde0023b15cc97c
- 1h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 6h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 24h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs

## 0x20cb8f872ae894f7c9e32e621c186e5afce82fd0
- 1h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 6h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 24h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs

## 0x3f9b863ef4b295d6ba370215bcca3785fcc44f44
- 1h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 6h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs
- 24h: protocol=n/a logs=0 unique=n/a top1=n/a top5=n/a dq=missing failure=no_swap_logs

## 0xe640781d47992636fe7dd4822f2cdf6cb7d5e331f346bc58776a577ecd493fea
- 1h: protocol=unsupported_pool_type logs= unique=n/a top1=n/a top5=n/a dq=unsupported failure=unsupported_pool_type
- 6h: protocol=unsupported_pool_type logs= unique=n/a top1=n/a top5=n/a dq=unsupported failure=unsupported_pool_type
- 24h: protocol=unsupported_pool_type logs= unique=n/a top1=n/a top5=n/a dq=unsupported failure=unsupported_pool_type
