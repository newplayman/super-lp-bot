from scripts.lp_tp_d_compare_v1_readonly import compare


def _row(identity, stable, frac, gate_netcover=False, **extra):
    gates = {
        "status_ok": True,
        "quality": True,
        "yield_cover": True,
        "stable": stable,
        "netcover_shadow": gate_netcover,
        "position_cap": True,
    }
    return {
        "llama_pool_id": identity,
        "symbol": identity,
        "resolve_status": "OK",
        "tier_quality": "A",
        "yield_cover": 2.0,
        "stable": stable,
        "enter_frac": frac,
        "entry_eligible": True,
        "netcover_pass": gate_netcover,
        "position_cap_pass": True,
        "gates": gates,
        **extra,
    }


def test_compare_reports_both_same_batch_flip_directions():
    old = [_row("a", True, 0.833), _row("b", False, 0.667)]
    new = [
        _row("a", False, 0.6, same_batch_former_stable=True,
             same_batch_former_enter_frac=0.833, same_batch_former_n_enter=5),
        _row("b", True, 0.7, same_batch_former_stable=False,
             same_batch_former_enter_frac=0.667, same_batch_former_n_enter=4),
    ]
    result = compare(old, new)
    d2 = result["same_batch_d2"]
    assert [row["llama_pool_id"] for row in d2["pass_to_fail"]] == ["a"]
    assert [row["llama_pool_id"] for row in d2["fail_to_pass"]] == ["b"]
    assert result["thresholds_unchanged"] == {
        "stable_min_frac": 0.7, "netcover_min": 1.0,
    }
