# V3 Pool State Failure Diagnosis

- `0x4e962bb3889bf030368f56810a9c96b83cb3e778` `cbBTC/USDC` root_cause=`abi_decode_error` fixability=`hard` recommended_fix=`treat as unsupported_pool_variant unless protocol-specific decoder is added`
- `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59` `WETH/USDC` root_cause=`abi_decode_error` fixability=`hard` recommended_fix=`treat as unsupported_pool_variant unless protocol-specific decoder is added`
- `0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1` `cbBTC/WETH` root_cause=`abi_decode_error` fixability=`hard` recommended_fix=`treat as unsupported_pool_variant unless protocol-specific decoder is added`
- `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` `WETH/USDC` root_cause=`unknown` fixability=`easy` recommended_fix=`use as v2 prevalidated standard v3 pool`
- `0x3f0296bf652e19bca772ec3df08b32732f93014a` `VIRTUAL/WETH` root_cause=`abi_decode_error` fixability=`hard` recommended_fix=`treat as unsupported_pool_variant unless protocol-specific decoder is added`
- `0x7ec6c9d993d9832aa654593f2dbc21303650bc6c` `0xACFE6019ED1A7DC6F7B508C02D1B04EC88CC21BF/WETH` root_cause=`abi_decode_error` fixability=`hard` recommended_fix=`treat as unsupported_pool_variant unless protocol-specific decoder is added`
