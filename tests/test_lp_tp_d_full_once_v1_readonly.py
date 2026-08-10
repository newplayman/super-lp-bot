from scripts.lp_tp_d_full_once_v1_readonly import (
    PhysicalRequestCounter,
    conservative_rpc_budget,
)


def test_physical_counter_distinguishes_success_and_rpc_error():
    counter = PhysicalRequestCounter()
    calls = iter([{"result": "0x1"}, {"error": {"code": -1}}])
    counter_post = __import__(
        "scripts.lp_tp_d_full_once_v1_readonly", fromlist=["rpc_module"]
    ).rpc_module
    original = counter_post._default_post
    counter_post._default_post = lambda *_args, **_kwargs: next(calls)
    try:
        counter.post("https://one", "eth_blockNumber", [])
        counter.post("https://one", "eth_call", [])
    finally:
        counter_post._default_post = original
    evidence = counter.evidence()
    assert evidence["physical_attempts_total"] == 2
    assert evidence["successes_by_method"] == {"eth_blockNumber": 1}
    assert evidence["failures_by_method"] == {"eth_call": 1}


def test_top_68_ten_window_worst_case_stays_below_old_92_by_6_budget():
    budget = conservative_rpc_budget(68)
    assert budget["old"]["total"] == 18_675
    assert budget["new"]["total"] == 18_497
    assert budget["delta"] == -178
    assert budget["within_old_budget"] is True
    assert conservative_rpc_budget(69)["within_old_budget"] is False
