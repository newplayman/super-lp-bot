# INVALIDATED — target-only research rows became accepted

This run is not acceptance or correlation evidence. Two rows selected only by
the ADD-2 target expansion (`CADC-USDC` and `XSGD-USDC`) failed the coarse TVL
gate but later passed the mathematical NetCover gate, so the operational SQLite
derivation recorded them as accepted. Target expansion must never act as a
production-selection whitelist. The run is invalid in full, including its
reported correlation, and must be replaced by a new stamp after target-only
rows are forced non-production while retaining their research NetCover values.
