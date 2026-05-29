# Tier C Next Action Decision

- current MICRO_CANDIDATE keep as MICRO: `no`
- WATCH continue count: `0`
- downgrade to REJECT count: `4`
- downgrade REJECT pools for current batch: `0x7cb770d0513c30e0cb45e4899e4a2cbeed6f9830`, `0x82dbe18346a8656dbb5e76f74bf3ae279cc16b29`, `0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa`, `0xe47f7dba68a00dc1a6f11458bcdfca810e1cfebf`
- best short-horizon p10 near zero found: `no`
- combined strict filter verdict: `REJECT`
- continue Tier C OOS on current batch: `no`
- stop current Tier C batch: `yes`
- rerun discovery for new pools: `yes`
- recommended_next_stage: `TIER_C_BATCH_REJECT_AND_REDISCOVER`

结论：当前 Tier C batch 在 proof 层过滤后仍然不存在可接受的短周期 tail。当前 batch 不继续 OOS，改为结束本批并重跑 discovery。
