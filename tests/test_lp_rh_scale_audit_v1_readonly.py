"""Tests for the RH-09a cross-scale consistency audit (pure, no network)."""
from __future__ import annotations

import json
import os
from decimal import Decimal

from scripts.lp_rh_scale_audit_v1_readonly import (
    audit_all,
    audit_module_prices,
    decimals_roundtrip_check,
    main,
    scale_invariance_check,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NETCOVER = os.path.join(REPO_ROOT, "scripts", "lp_rh_netcover_inputs_v1_readonly.py")
COLLECTOR = os.path.join(REPO_ROOT, "scripts", "lp_rh_collector_v1_readonly.py")

RAW_PRICE = Decimal("2.490581295882323411599032826E-9")
NORM_PRICE = Decimal("2490.581295882323411599032826")
LIQ = Decimal("10000000")
FEE = Decimal("0.001")
SCALES = [Decimal(x) for x in (50, 500, 5000, 50000)]


def _cost_share(price):
    """Cost as a fraction of position: fixed fee share + price-impact share."""
    def f(pos):
        return FEE + pos / (LIQ * price)
    return f


def test_bug_repro_raw_ratio_violation():
    # raw ratio used as price -> cost/position grows with size -> not constant
    res = scale_invariance_check(_cost_share(RAW_PRICE), base_kwargs={}, scale_key="pos", scales=SCALES, expected="CONSTANT")
    assert res["verdict"] == "VIOLATION"


def test_bug_repro_normalized_ok():
    # decimals-normalised price -> cost/position ~constant across sizes
    res = scale_invariance_check(_cost_share(NORM_PRICE), base_kwargs={}, scale_key="pos", scales=SCALES, expected="CONSTANT")
    assert res["verdict"] == "OK"


def test_roundtrip_correct_decimals():
    res = decimals_roundtrip_check(sqrt_price_x96=3953938817749275760872870, dec0=18, dec1=6)
    assert res["ratio"] == 10 ** 12
    assert Decimal("2490") <= res["human"] <= Decimal("2491")
    assert res["ok"] is True


def test_roundtrip_wrong_dec1():
    res = decimals_roundtrip_check(sqrt_price_x96=3953938817749275760872870, dec0=18, dec1=18)
    assert res["ratio"] == 1
    # human collapses to the raw ratio, not a real pool price
    assert res["human"] < Decimal("1")


def test_linear_ok():
    res = scale_invariance_check(lambda pos: 2 * pos, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10), Decimal(100)], expected="LINEAR")
    assert res["verdict"] == "OK"


def test_linear_violation():
    res = scale_invariance_check(lambda pos: pos * pos, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10), Decimal(100)], expected="LINEAR")
    assert res["verdict"] == "VIOLATION"


def test_constant_ok():
    res = scale_invariance_check(lambda pos: 5, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10), Decimal(100)], expected="CONSTANT")
    assert res["verdict"] == "OK"


def test_constant_violation():
    res = scale_invariance_check(lambda pos: pos, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10), Decimal(100)], expected="CONSTANT")
    assert res["verdict"] == "VIOLATION"


def test_sublinear_ok():
    res = scale_invariance_check(lambda pos: pos * (1 + pos / 1000), base_kwargs={}, scale_key="pos", scales=[Decimal(100), Decimal(200), Decimal(300)], expected="SUBLINEAR")
    assert res["verdict"] == "OK"


def test_sublinear_violation():
    res = scale_invariance_check(lambda pos: pos * (1 + pos / 10), base_kwargs={}, scale_key="pos", scales=[Decimal(10), Decimal(100), Decimal(1000)], expected="SUBLINEAR")
    assert res["verdict"] == "VIOLATION"


def test_none_input_unavailable():
    def f(pos):
        return None if pos > 100 else pos
    res = scale_invariance_check(f, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10), Decimal(100), Decimal(1000)], expected="LINEAR")
    assert res["verdict"] == "INPUTS_UNAVAILABLE"
    assert res["verdict"] != "VIOLATION"
    assert res["verdict"] != "OK"


def test_audit_flags_raw_ratio_no_scaling():
    src = "price = (sqrt_price_x96 / 2.0 ** 96) ** 2\n"
    findings = audit_module_prices("fake", src)
    assert len(findings) == 1
    assert findings[0]["risk"] == "RAW_RATIO_USED_AS_PRICE"


def test_audit_no_flag_with_scaling():
    src = "price = ((sqrt_price_x96 / 2.0 ** 96) ** 2) * (10 ** d0) / (10 ** d1)\n"
    assert audit_module_prices("fake", src) == []


def test_audit_heuristic_flag():
    src = "price = (sqrt_price_x96 / 2.0 ** 96) ** 2\n"
    findings = audit_module_prices("fake", src)
    assert findings[0]["heuristic"] is True


def test_audit_netcover_no_flag():
    # real regression: the fixed assembler must no longer be flagged
    with open(NETCOVER, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert audit_module_prices("netcover", src) == []


def test_audit_collector_no_flag():
    # real regression: compute_price_human has the scaling within 5 lines
    with open(COLLECTOR, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert audit_module_prices("collector", src) == []


def test_audit_all_structure(tmp_path):
    (tmp_path / "lp_rh_fake_bad.py").write_text(
        "price = (sqrt_price_x96 / 2.0 ** 96) ** 2\n")
    (tmp_path / "lp_rh_fake_good.py").write_text(
        "price = ((sqrt_price_x96 / 2.0 ** 96) ** 2) * (10 ** d0) / (10 ** d1)\n")
    result = audit_all(str(tmp_path))
    assert result["modules_scanned"] == 2
    assert result["modules_with_findings"] == 1
    assert "lp_rh_fake_bad.py" in result["findings"]
    assert "lp_rh_fake_good.py" not in result["findings"]


def test_main_writes_out(tmp_path):
    (tmp_path / "lp_rh_fake_bad.py").write_text(
        "price = (sqrt_price_x96 / 2.0 ** 96) ** 2\n")
    out = tmp_path / "out.json"
    rc = main(["--scripts-dir", str(tmp_path), "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["modules_with_findings"] == 1


def test_scale_check_return_keys():
    res = scale_invariance_check(lambda pos: 2 * pos, base_kwargs={}, scale_key="pos", scales=[Decimal(1), Decimal(10)], expected="LINEAR")
    for key in ("scales", "values", "ratios", "expected", "verdict", "detail"):
        assert key in res


def test_roundtrip_return_keys():
    res = decimals_roundtrip_check(sqrt_price_x96=3953938817749275760872870, dec0=18, dec1=6)
    for key in ("raw", "human", "ratio", "expected_ratio", "ok"):
        assert key in res
