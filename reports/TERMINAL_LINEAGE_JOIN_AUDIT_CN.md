# Terminal Lineage Join Audit

- positions table present: yes

| horizon | terminal rows total | decision_trace_id join via id success count | decision_trace_id join via trace_id success count | position_id join success count | positions.id join success count | pool_id resolved count | UNKNOWN pool count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 24h | 14047 | 0 | 14047 | 14047 | 14047 | 14047 | 0 |
| 6h | 5683 | 0 | 5683 | 5683 | 5683 | 5683 | 0 |

## Root Cause Distribution

| horizon | root_cause | count |
| --- | --- | ---: |
| 24h | id_vs_trace_id_mismatch | 14047 |
| 6h | id_vs_trace_id_mismatch | 5683 |

## UNKNOWN Pool / Join-Failed Samples

| horizon | repaired decision_trace_id | matched shadow_decision_trace.id? | matched shadow_decision_trace.trace_id? | position_id | pool_id | exit_decision exists? | exit_action exists? | nearest same-position mark exists? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 24h | shadow-trace-000aeeb6850fcafd958bfb26 | no | yes | shadow-pos-d242d4f81bdc2b874e602b7a | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-000ea85f6e142f0ffdfb4df8 | no | yes | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-0010f570a3a888ffaa94e03b | no | yes | shadow-pos-ed4a00d22f941ea02c4a9abb | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0012eba3083d0b3000693619 | no | yes | shadow-pos-b2b74e0686d4ef35496581ed | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | yes | yes | yes |
| 24h | shadow-trace-0018c31270d6f4d5ed37eece | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0019b33c83aacd0b34b8e062 | no | yes | shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-00201f717d804d3ae83aa5af | no | yes | shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-0021e8d9f0b0ff53cc95157a | no | yes | shadow-pos-7f17b03d5f6152b6f693864d | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | yes | yes | yes |
| 24h | shadow-trace-0023b358d3817ac84e5867ba | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0024625a1136f4c417eab122 | no | yes | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-002bca6cba6a1f85b53234a6 | no | yes | shadow-pos-e578fab5031843ede06449c2 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-003220636370534ce0fb4223 | no | yes | shadow-pos-91d83562aa038c689fc52a49 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00338eeded47df87da530c06 | no | yes | shadow-pos-f823ae9a69be0b66cb778ba8 | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-0034f37ed0842424c701fbc1 | no | yes | shadow-pos-824c6f5ed8b582da1b0004a6 | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-003668dbae16fdae7219ce53 | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-003860452bef2b1cf278b077 | no | yes | shadow-pos-d242d4f81bdc2b874e602b7a | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00395f8fa9dc29efd00e2b75 | no | yes | shadow-pos-257085443f2329f36ad3ad97 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-003e0f6e8feffc6a88050ec1 | no | yes | shadow-pos-d242d4f81bdc2b874e602b7a | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-004056ef2df7f4fba90bedea | no | yes | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-00431bae7eb866d0ebf0a21c | no | yes | shadow-pos-e578fab5031843ede06449c2 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00441f650cfb5a43ef1a4bc5 | no | yes | shadow-pos-91d83562aa038c689fc52a49 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-004a8eee8916cc8ffe06a384 | no | yes | shadow-pos-06eb7de3f0c56598add9777c | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-004e7823be1b7b96e9a43b77 | no | yes | shadow-pos-f823ae9a69be0b66cb778ba8 | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-0050ff4b0000697bc292cb9c | no | yes | shadow-pos-c5e8f94d64e82415136312e3 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-00587d051cea7d767bbc143f | no | yes | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-0065299d2327b0c685ffd3f9 | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0067d548d2d37ad7242ba909 | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00699bc990729bd4737ee045 | no | yes | shadow-pos-d242d4f81bdc2b874e602b7a | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0069e0e3637991405c98e4e3 | no | yes | shadow-pos-91d83562aa038c689fc52a49 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-006a224337b11e776f87c4e5 | no | yes | shadow-pos-7f17b03d5f6152b6f693864d | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | yes | yes | yes |
| 24h | shadow-trace-006b592bc99784568a6e70db | no | yes | shadow-pos-7f17b03d5f6152b6f693864d | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | yes | yes | yes |
| 24h | shadow-trace-006c602305871b0e04f1a64d | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-0075eef22434f0fc57eb7540 | no | yes | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-0076d1f65bd5a36aaff84ac0 | no | yes | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-007b15dcd47b1aa2c49a5117 | no | yes | shadow-pos-bad539974a504c8a7456e535 | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-007b84c3764299cf7408afe2 | no | yes | shadow-pos-5bbfdd99de9f74905e0a31af | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-007c05d22f177c7715127578 | no | yes | shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-007ea8a599437f433410c6f8 | no | yes | shadow-pos-7efaae8b9be88674cd389b29 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-008882eeaccbc198e6998778 | no | yes | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-008fc87ea85a3a67fd9d2ff9 | no | yes | shadow-pos-68ad1af5798162ee842fb8a8 | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-0092af8ef497a7d30a94cf4c | no | yes | shadow-pos-b2b74e0686d4ef35496581ed | 0x6c561b446416e1a00e8e93e221854d6ea4171372 | yes | yes | yes |
| 24h | shadow-trace-009f3f6973f940a1f5dc45ca | no | yes | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-00a12e36eb08699e513136e8 | no | yes | shadow-pos-b56917c6282e10d8858782aa | 0x4e962bb3889bf030368f56810a9c96b83cb3e778 | yes | yes | yes |
| 24h | shadow-trace-00a235c8f9b3f7846c9e865a | no | yes | shadow-pos-9878cd860310b5e6e2eb81b4 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00a353a4a2bbc6fdb0f1c992 | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00a651dee35f94990dfa137d | no | yes | shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | yes | yes | yes |
| 24h | shadow-trace-00a9a4932c30633ad5993e9e | no | yes | shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | yes | yes | yes |
| 24h | shadow-trace-00b16ce39d3ec17df2a59faa | no | yes | shadow-pos-fbeaeba5f113d78d37c03530 | 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1 | yes | yes | yes |
| 24h | shadow-trace-00c05d417032c6c5c482db20 | no | yes | shadow-pos-833713bf8f5b4cb1b0c6bf63 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
| 24h | shadow-trace-00c0f0e9baad7338a459ce6c | no | yes | shadow-pos-842896745e4337f71da620a9 | 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 | yes | yes | yes |
