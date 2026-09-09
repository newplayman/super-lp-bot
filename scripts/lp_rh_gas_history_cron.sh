#!/usr/bin/env bash
# Record one gas observation. Native price is the collector's latest WETH/USDG
# pool mid -- the same figure RH-03d uses -- so the two agree by construction.
# Writes nothing when the price is unavailable: a gap is honest, a placeholder
# is not.
set -u
ROOT=/opt/lpbot/lp-bot-v3-origin-check
PY=/root/lp-bot/.venv/bin/python
DB="$ROOT/reports/lp_rh/gas_history.db"

ETH=$("$PY" - <<'PYEOF' 2>/dev/null
import sqlite3
try:
    c = sqlite3.connect("/opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db")
    r = c.execute("SELECT reference_mid FROM rh_market_states "
                  "WHERE reference_mid IS NOT NULL "
                  "ORDER BY rowid DESC LIMIT 1").fetchone()
    print(r[0] if r else "")
except Exception:
    print("")
PYEOF
)
[ -z "$ETH" ] && exit 0        # no price -> no observation, and no error either

cd "$ROOT" && "$PY" scripts/lp_rh_gas_history_v1_readonly.py \
    --db "$DB" --native-price-usd "$ETH" --once >/dev/null 2>&1
