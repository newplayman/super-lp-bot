import json
import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts import lp_rh_size_interval_v1_readonly as mod


# --- T31 core scenario ------------------------------------------------------

def test_t31_empty_interval_width_negative():
    # q_min=60 > q_max=40: the audited T31 case.
    result = mod.size_interval(q_min=60, q_max=40)
    assert result["status"] == "SIZE_INTERVAL_EMPTY"
    assert result["width"] == Decimal(-20)
    assert result["width"] < 0


def test_computed_interval():
    result = mod.size_interval(q_min=40, q_max=60)
    assert result["status"] == "COMPUTED"
    assert result["width"] == Decimal(20)
    assert result["width"] > 0
    assert mod.is_actionable(result) is True


def test_point_interval_is_feasible():
    # A point interval is legal: exactly one feasible size, not "empty".
    result = mod.size_interval(q_min=50, q_max=50)
    assert result["status"] == "SIZE_INTERVAL_POINT"
    assert result["width"] == Decimal(0)
    assert result["width"] is not None
    assert mod.is_actionable(result) is True


# --- missing inputs ---------------------------------------------------------

def test_q_min_none_inputs_unavailable():
    result = mod.size_interval(q_min=None, q_max=60)
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["width"] is None
    assert result["q_min"] is None


def test_q_max_none_inputs_unavailable():
    result = mod.size_interval(q_min=40, q_max=None)
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["width"] is None
    assert result["q_max"] is None


def test_both_none_inputs_unavailable():
    result = mod.size_interval(q_min=None, q_max=None)
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["width"] is None


def test_empty_status_differs_from_unavailable():
    # Dedicated guard: an empty interval is a computed conclusion, not
    # missing data.  Merging the two statuses would send operators to
    # fetch data instead of switching pools.
    empty = mod.size_interval(q_min=60, q_max=40)
    missing = mod.size_interval(q_min=None, q_max=60)
    assert empty["status"] != missing["status"]
    assert empty["status"] == "SIZE_INTERVAL_EMPTY"
    assert missing["status"] == "INPUTS_UNAVAILABLE"
    assert empty["width"] is not None
    assert missing["width"] is None


# --- is_actionable: one assertion per status --------------------------------

def test_is_actionable_computed_true():
    assert mod.is_actionable(mod.size_interval(q_min=40, q_max=60)) is True


def test_is_actionable_point_true():
    assert mod.is_actionable(mod.size_interval(q_min=50, q_max=50)) is True


def test_is_actionable_empty_false():
    assert mod.is_actionable(mod.size_interval(q_min=60, q_max=40)) is False


def test_is_actionable_unavailable_false():
    assert mod.is_actionable(mod.size_interval(q_min=None, q_max=60)) is False


# --- clamp_to_interval ------------------------------------------------------

def test_clamp_empty_interval_returns_none():
    empty = mod.size_interval(q_min=60, q_max=40)
    assert mod.clamp_to_interval(50, empty) is None  # not 40, not 60


def test_clamp_below_lower_bound():
    interval = mod.size_interval(q_min=40, q_max=60)
    assert mod.clamp_to_interval(30, interval) == Decimal(40)


def test_clamp_above_upper_bound():
    interval = mod.size_interval(q_min=40, q_max=60)
    assert mod.clamp_to_interval(80, interval) == Decimal(60)


def test_clamp_inside_interval_unchanged():
    interval = mod.size_interval(q_min=40, q_max=60)
    assert mod.clamp_to_interval(50, interval) == Decimal(50)


def test_clamp_point_interval_collapses_to_point():
    point = mod.size_interval(q_min=50, q_max=50)
    assert mod.clamp_to_interval(30, point) == Decimal(50)
    assert mod.clamp_to_interval(80, point) == Decimal(50)


def test_clamp_unavailable_interval_returns_none():
    missing = mod.size_interval(q_min=None, q_max=60)
    assert mod.clamp_to_interval(50, missing) is None


def test_clamp_missing_size_returns_none():
    interval = mod.size_interval(q_min=40, q_max=60)
    assert mod.clamp_to_interval(None, interval) is None


# --- types ------------------------------------------------------------------

def test_all_values_decimal_not_float():
    for kwargs in ({"q_min": 40, "q_max": 60},
                   {"q_min": 60, "q_max": 40},
                   {"q_min": 50, "q_max": 50}):
        result = mod.size_interval(**kwargs)
        for key in ("q_min", "q_max", "width"):
            assert isinstance(result[key], Decimal), (key, kwargs)
            assert not isinstance(result[key], float), (key, kwargs)
        clamped = mod.clamp_to_interval(Decimal(55), result)
        if clamped is not None:
            assert isinstance(clamped, Decimal)
            assert not isinstance(clamped, float)


def test_string_inputs_coerced_to_decimal():
    result = mod.size_interval(q_min="40", q_max="60")
    assert result["status"] == "COMPUTED"
    assert result["width"] == Decimal(20)
    assert isinstance(result["q_min"], Decimal)


def test_empty_reason_mentions_both_boundaries():
    result = mod.size_interval(q_min=60, q_max=40)
    assert "60" in result["reason"]
    assert "40" in result["reason"]


# --- CLI --------------------------------------------------------------------

def test_main_cli_writes_json(tmp_path):
    out = tmp_path / "interval.json"
    rc = mod.main(["--q-min", "60", "--q-max", "40", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["status"] == "SIZE_INTERVAL_EMPTY"
    assert payload["width"] == "-20"


def test_main_cli_missing_inputs(tmp_path):
    out = tmp_path / "interval.json"
    rc = mod.main(["--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["status"] == "INPUTS_UNAVAILABLE"
    assert payload["width"] is None
