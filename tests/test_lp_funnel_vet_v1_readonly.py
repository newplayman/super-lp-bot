"""Pure tests for the funnel vetting merge (no network)."""
from scripts.lp_funnel_vet_v1_readonly import (
    _yc_value,
    _pool_key,
    index_stability,
    vet_record,
    funnel_vet,
    vetted_menu,
)


def test_yc_value_coercion():
    assert _yc_value(8.2) == 8.2
    assert _yc_value("inf") == float("inf")
    assert _yc_value(None) == 0.0
    assert _yc_value("garbage") == 0.0


def test_pool_key_prefers_resolved_lowercased():
    assert _pool_key({"resolved_pool": "0xAbC", "pool": "uuid"}) == "0xabc"
    assert _pool_key({"pool": "0xDEF"}) == "0xdef"
    assert _pool_key({}) == ""


def test_index_stability_by_addr():
    s = [{"pool": "0xAAA", "fee_cover_stability": {"stable": True, "enter_frac": 0.8}}]
    idx = index_stability(s)
    assert idx["0xaaa"]["stable"] is True


def _b(sym, q, yc, pool, wash=False, status="OK", resolve="OK"):
    return {"symbol": sym, "tier_quality": q, "yield_cover": yc, "wash_flag": wash,
            "status": status, "resolve_status": resolve, "resolved_pool": pool}


def test_vet_record_all_gates_pass():
    r = vet_record(
        _b("G", "B", 8.2, "0xAAA"), {"stable": True, "enter_frac": 0.83},
        require_netcover=False,
    )
    assert r["vetted"] is True
    assert r["gates"] == {"quality": True, "yield_cover": True, "stable": True, "status_ok": True}
    assert r["stable"] is True and r["enter_frac"] == 0.83


def test_vet_record_each_gate_can_fail():
    # unstable
    assert vet_record(_b("U", "B", 14, "0xB"), {"stable": False}, require_netcover=False)["vetted"] is False
    # low yield_cover
    assert vet_record(_b("L", "A", 0.4, "0xC"), {"stable": True}, require_netcover=False)["vetted"] is False
    # bad quality tier
    assert vet_record(_b("J", "C", 99, "0xD"), {"stable": True}, require_netcover=False)["vetted"] is False
    # wash-flagged
    assert vet_record(_b("W", "B", 50, "0xE", wash=True), {"stable": True}, require_netcover=False)["vetted"] is False
    # unresolved
    assert vet_record(_b("N", "B", 50, "0xF", resolve="NOT_FOUND"), {"stable": True}, require_netcover=False)["vetted"] is False


def test_vet_record_inf_yc_passes_yield_gate():
    r = vet_record(_b("I", "A", "inf", "0xA"), {"stable": True}, require_netcover=False)
    assert r["gates"]["yield_cover"] is True and r["vetted"] is True


def test_funnel_vet_and_menu_end_to_end():
    bridge = [
        _b("GOOD", "B", 8.2, "0xAAA"),
        _b("UNSTABLE", "B", 14.0, "0xBBB"),
        _b("LOWYC", "A", 0.4, "0xCCC"),
        _b("BEST", "A", 30.0, "0xFFF"),
    ]
    stab = [
        {"pool": "0xaaa", "fee_cover_stability": {"stable": True, "enter_frac": 0.83}},
        {"pool": "0xbbb", "fee_cover_stability": {"stable": False, "enter_frac": 0.33}},
        {"pool": "0xccc", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}},
        {"pool": "0xfff", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}},
    ]
    menu = vetted_menu(funnel_vet(bridge, stab, allow_legacy_without_netcover=True))
    # GOOD + BEST pass; sorted by yc desc => BEST first
    assert [r["symbol"] for r in menu] == ["BEST", "GOOD"]


def test_missing_stability_means_not_stable():
    # a bridge record with no stability entry must NOT pass (fluke-protection default)
    merged = funnel_vet(
        [_b("ORPHAN", "B", 9.0, "0xZZZ")], [],
        allow_legacy_without_netcover=True,
    )
    assert merged[0]["vetted"] is False and merged[0]["stable"] is False


def test_fifth_gate_rejects_below_shadow_netcover():
    bridge = [_b("LOW_NETCOVER", "A", 20.0, "0xAAA")]
    stability = [{"pool": "0xaaa", "fee_cover_stability": {"stable": True}}]
    netcover = [{"pool": "0xaaa", "netcover": 0.99}]
    rec = funnel_vet(bridge, stability, netcover_records=netcover)[0]
    assert rec["gates"]["netcover_shadow"] is False
    assert rec["vetted"] is False


def test_fifth_gate_passes_at_exact_inv_gate_01_threshold():
    bridge = [_b("AT_THRESHOLD", "A", 20.0, "0xAAA")]
    stability = [{"pool": "0xaaa", "fee_cover_stability": {"stable": True}}]
    netcover = [{"resolved_pool": "0xAAA", "netcover": 1.0}]
    rec = funnel_vet(bridge, stability, netcover_records=netcover)[0]
    assert rec["gates"]["netcover_shadow"] is True
    assert rec["netcover"] == 1.0
    assert rec["vetted"] is True


def test_explicit_netcover_mode_fails_closed_when_pool_has_no_score():
    bridge = [_b("MISSING", "A", 20.0, "0xAAA")]
    stability = [{"pool": "0xaaa", "fee_cover_stability": {"stable": True}}]
    rec = funnel_vet(bridge, stability, netcover_records=[])[0]
    assert rec["gates"]["netcover_shadow"] is False
    assert rec["netcover_gate_status"] == "MISSING_FAIL_CLOSED"
    assert rec["vetted"] is False


def test_default_funnel_is_fail_closed_without_netcover():
    bridge = [_b("NO_BYPASS", "A", 20.0, "0xAAA")]
    stability = [{"pool": "0xaaa", "fee_cover_stability": {"stable": True}}]
    rec = funnel_vet(bridge, stability)[0]
    assert rec["gates"]["netcover_shadow"] is False
    assert rec["netcover_gate_status"] == "MISSING_FAIL_CLOSED"
    assert rec["vetted"] is False
