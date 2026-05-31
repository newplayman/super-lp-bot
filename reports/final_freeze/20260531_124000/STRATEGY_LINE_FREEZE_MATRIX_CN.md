# 策略线冻结矩阵

- `current_full_strategy`: `FAIL` | reason: position_lifecycle primary proof 下 tail 不可接受 | reopen: new proof unit or new data/strategy assumption
- `fixed_horizon_position_lifecycle`: `STOP` | reason: 12h fail, 24h insufficient, position reuse dominant | reopen: new sample source not blocked by reuse
- `intent_lifecycle`: `STOP` | reason: DQ 修正后无 stable review-ready signal | reopen: new intent proof design + better entry notional lineage
- `Tier B discovery/data-fix`: `PAUSE` | reason: no research candidate with enough data quality | reopen: stronger data source and new candidate set
- `Tier C batch`: `REJECTED` | reason: holder/trader concentration extreme, batch frozen | reopen: new market change and rediscovery only
- `Risk-Aware Short-Hold exit`: `STOP` | reason: risk_exit not helpful, quarantine only helpful | reopen: new risk signal family with practical retention
- `Pool Regime Classifier`: `PAUSE` | reason: 有尾部解释力，但只能做过滤解释，不足以独立成策略 | reopen: serve as feature only under new strategy frame
- `Pool Regime Aware Short-Hold`: `STOP` | reason: leakage fixed 后 retention 太低，误杀太高 | reopen: new practical gate pass with non-overfiltering behavior
- `Fee Velocity / Exit Depth`: `STOP` | reason: no practical variant passed, fee-cost still negative or retention too low | reopen: new fee/depth data pipeline and strategy redesign
- `Overall LP research line`: `STOP` | reason: P0/P1/P2 全部未形成可实用研究候选 | reopen: new data source first or full hypothesis redesign
