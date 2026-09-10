import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts import lp_rh_gas_estimator_v1_readonly as mod


# --- estimate_gas_usd -------------------------------------------------------

def test_estimate_gas_usd_measured_anchor():
    # T34 measured value: 800000 gas @ 232188000 wei, native $2484 -> ~$0.4614.
    result = mod.estimate_gas_usd(
        gas_price_wei=232188000,
        native_price_usd=2484,
        gas_units=800000,
    )
    assert result is not None
    assert Decimal("0.46") < result < Decimal("0.47")


def test_estimate_gas_usd_none_gas_price():
    assert mod.estimate_gas_usd(
        gas_price_wei=None, native_price_usd=2484, gas_units=800000,
    ) is None


def test_estimate_gas_usd_none_native_price():
    assert mod.estimate_gas_usd(
        gas_price_wei=232188000, native_price_usd=None, gas_units=800000,
    ) is None


def test_estimate_gas_usd_none_gas_units():
    assert mod.estimate_gas_usd(
        gas_price_wei=232188000, native_price_usd=2484, gas_units=None,
    ) is None


def test_estimate_gas_usd_zero_gas_price():
    # zero must yield None, not 0.
    assert mod.estimate_gas_usd(
        gas_price_wei=0, native_price_usd=2484, gas_units=800000,
    ) is None


def test_estimate_gas_usd_returns_decimal():
    result = mod.estimate_gas_usd(
        gas_price_wei=232188000, native_price_usd=2484, gas_units=800000,
    )
    assert isinstance(result, Decimal)
    assert not isinstance(result, float)


def test_round_trip_gas_usd_matches_anchor():
    # v3_mint + v3_burn_collect == 450000 + 350000 == 800000 gas units.
    assert mod.GAS_UNITS["v3_mint"] + mod.GAS_UNITS["v3_burn_collect"] == 800000
    result = mod.round_trip_gas_usd(gas_price_wei=232188000, native_price_usd=2484)
    assert result is not None
    assert Decimal("0.46") < result < Decimal("0.47")


# --- observed_gas_units -----------------------------------------------------

def test_observed_gas_units_empty():
    stats = mod.observed_gas_units([])
    assert stats["n"] == 0
    assert stats["median_gas_used"] is None
    assert stats["median_gas_price_wei"] is None
    assert stats["p90_gas_used"] is None


def test_observed_gas_units_median():
    receipts = [{"gasUsed": v, "effectiveGasPrice": 1} for v in (100, 200, 300)]
    stats = mod.observed_gas_units(receipts)
    assert stats["n"] == 3
    assert stats["median_gas_used"] == 200


def test_observed_gas_units_p90():
    receipts = [{"gasUsed": v, "effectiveGasPrice": 1} for v in (100, 200, 300)]
    stats = mod.observed_gas_units(receipts)
    # linear interpolation: 200 + 0.8 * (300 - 200) == 280
    assert stats["p90_gas_used"] == 280


# --- gas_estimate_sanity ----------------------------------------------------

def test_sanity_understated_reproduces_error():
    # The main brain's 0.02 vs the measured 0.4614 -> ~23x understated.
    result = mod.gas_estimate_sanity(Decimal("0.02"), Decimal("0.4614"))
    assert result["verdict"] == "UNDERSTATED"
    assert Decimal("0.042") < result["ratio"] < Decimal("0.044")


def test_sanity_ok():
    result = mod.gas_estimate_sanity(Decimal("0.4614"), Decimal("0.4614"))
    assert result["verdict"] == "OK"
    assert isinstance(result["ratio"], Decimal)
    assert abs(result["ratio"] - Decimal(1)) < Decimal("0.001")


def test_sanity_overstated():
    result = mod.gas_estimate_sanity(Decimal("2.0"), Decimal("0.4614"))
    assert result["verdict"] == "OVERSTATED"
    assert result["ratio"] > Decimal(3)


def test_sanity_unknown_when_estimate_none():
    result = mod.gas_estimate_sanity(None, Decimal("0.4614"))
    assert result["verdict"] == "UNKNOWN"
    assert result["ratio"] is None


def test_sanity_unknown_when_observed_none():
    result = mod.gas_estimate_sanity(Decimal("0.4614"), None)
    assert result["verdict"] == "UNKNOWN"
    assert result["ratio"] is None


def test_sanity_boundary_low_is_ok():
    observed = Decimal("0.4614")
    max_ratio = Decimal("3")
    estimate = observed / max_ratio  # ratio exactly 1/max_ratio
    result = mod.gas_estimate_sanity(estimate, observed, max_ratio=max_ratio)
    assert result["verdict"] == "OK"
    assert abs(result["ratio"] - (Decimal(1) / max_ratio)) < Decimal("0.0001")


def test_sanity_boundary_high_is_ok():
    observed = Decimal("0.4614")
    max_ratio = Decimal("3")
    estimate = observed * max_ratio  # ratio exactly max_ratio
    result = mod.gas_estimate_sanity(estimate, observed, max_ratio=max_ratio)
    assert result["verdict"] == "OK"
    assert result["ratio"] == max_ratio


# --- GAS_UNITS --------------------------------------------------------------

def test_gas_units_keys_positive():
    for key in ("v3_mint", "v3_burn_collect", "swap"):
        assert key in mod.GAS_UNITS
        assert mod.GAS_UNITS[key] > 0


# --- observed_gas_usd (RH-02cg) ---------------------------------------------

def _create_gas_db(conn, rows=None):
    conn.execute(
        """
        CREATE TABLE rh_gas_observations (
            observed_at TEXT NOT NULL,
            gas_price_wei INTEGER,
            native_price_usd TEXT,
            gas_usd TEXT,
            block_number INTEGER,
            receipt_n INTEGER,
            source TEXT,
            PRIMARY KEY (observed_at, block_number)
        )
        """
    )
    if rows:
        for r in rows:
            conn.execute(
                "INSERT INTO rh_gas_observations "
                "(observed_at, gas_price_wei, native_price_usd, gas_usd, block_number, receipt_n, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                r,
            )
    conn.commit()


def test_observed_gas_usd_five_fresh_samples(tmp_path):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    now = "2026-09-10T12:00:00Z"
    # 5 samples within 1 hour
    rows = [
        ("2026-09-10T11:50:00Z", 100, "2500", "0.20", 1, 10, "test"),
        ("2026-09-10T11:40:00Z", 100, "2500", "0.22", 2, 10, "test"),
        ("2026-09-10T11:30:00Z", 100, "2500", "0.24", 3, 10, "test"),
        ("2026-09-10T11:20:00Z", 100, "2500", "0.26", 4, 10, "test"),
        ("2026-09-10T11:10:00Z", 100, "2500", "0.28", 5, 10, "test"),
    ]
    _create_gas_db(conn, rows)
    res = mod.observed_gas_usd(conn, now=now)
    assert res["reason"] == "OK"
    assert res["sample_count"] == 5
    assert res["gas_usd"] == Decimal("0.24")
    assert res["source"] == "observed"
    assert res["newest_observed_at"] == "2026-09-10T11:50:00Z"


def test_observed_gas_usd_table_missing():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    now = "2026-09-10T12:00:00Z"
    res = mod.observed_gas_usd(conn, now=now)
    assert res["gas_usd"] is None
    assert res["reason"] == "GAS_OBSERVATIONS_TABLE_MISSING"
    assert res["sample_count"] == 0


def test_observed_gas_usd_empty_table():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    _create_gas_db(conn, [])
    now = "2026-09-10T12:00:00Z"
    res = mod.observed_gas_usd(conn, now=now)
    assert res["gas_usd"] is None
    assert res["reason"] == "GAS_OBSERVATIONS_EMPTY"
    assert res["sample_count"] == 0


def test_observed_gas_usd_insufficient_samples():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    now = "2026-09-10T12:00:00Z"
    # 2 samples (< min_samples=3)
    rows = [
        ("2026-09-10T11:50:00Z", 100, "2500", "0.20", 1, 10, "test"),
        ("2026-09-10T11:40:00Z", 100, "2500", "0.22", 2, 10, "test"),
    ]
    _create_gas_db(conn, rows)
    res = mod.observed_gas_usd(conn, now=now)
    assert res["gas_usd"] is None
    assert res["reason"] == "GAS_OBSERVATIONS_INSUFFICIENT"
    assert res["sample_count"] == 2


def test_observed_gas_usd_stale():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    now = "2026-09-10T14:00:00Z"
    # Newest is 2 hours ago (> max_age_secs=3600)
    rows = [
        ("2026-09-10T12:00:00Z", 100, "2500", "0.20", 1, 10, "test"),
        ("2026-09-10T11:50:00Z", 100, "2500", "0.22", 2, 10, "test"),
        ("2026-09-10T11:40:00Z", 100, "2500", "0.24", 3, 10, "test"),
    ]
    _create_gas_db(conn, rows)
    res = mod.observed_gas_usd(conn, now=now, max_age_secs=3600)
    assert res["gas_usd"] is None
    assert res["reason"] == "GAS_OBSERVATIONS_STALE"
    assert res["newest_observed_at"] == "2026-09-10T12:00:00Z"


def test_observed_gas_usd_outlier_spike_resistance():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    now = "2026-09-10T12:00:00Z"
    # 5 samples, one is 100x spike
    rows = [
        ("2026-09-10T11:50:00Z", 100, "2500", "0.20", 1, 10, "test"),
        ("2026-09-10T11:45:00Z", 100, "2500", "0.21", 2, 10, "test"),
        ("2026-09-10T11:40:00Z", 100, "2500", "25.0", 3, 10, "test"),  # spike!
        ("2026-09-10T11:35:00Z", 100, "2500", "0.22", 4, 10, "test"),
        ("2026-09-10T11:30:00Z", 100, "2500", "0.23", 5, 10, "test"),
    ]
    _create_gas_db(conn, rows)
    res = mod.observed_gas_usd(conn, now=now)
    assert res["reason"] == "OK"
    assert res["sample_count"] == 5
    # Median of [0.20, 0.21, 0.22, 0.23, 25.0] is 0.22
    assert res["gas_usd"] == Decimal("0.22")
    assert res["gas_usd"] < Decimal("0.5")  # Not dragged by the spike

