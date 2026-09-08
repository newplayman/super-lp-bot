import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import hashlib
import json
import math
import time

from scripts.lp_rh_provider_pool_v1_readonly import (
    ProviderPool,
    detect_disagreement,
    live_readiness,
    usable_providers,
    verify_provider_methods,
)

PROVIDERS = [
    {"name": "p1", "url": "http://p1"},
    {"name": "p2", "url": "http://p2"},
    {"name": "p3", "url": "http://p3"},
]
METHODS = [
    {"method": "eth_chainId", "params": []},
    {"method": "eth_blockNumber", "params": []},
    {"method": "eth_call", "params": []},
    {"method": "eth_gasPrice", "params": []},
]
URL_TO_NAME = {p["url"]: p["name"] for p in PROVIDERS}
METHOD_NAMES = [m["method"] for m in METHODS]


def make_call_fn(overrides=None, errors=None):
    """Offline fake call_fn. By default every provider returns the same value
    for a given method (so digests agree); ``overrides``/``errors`` key on
    ``(provider_name, method_name)``."""
    overrides = overrides or {}
    errors = errors or {}

    def call_fn(url, method, params):
        name = URL_TO_NAME[url]
        key = (name, method)
        if key in errors:
            raise errors[key]
        if key in overrides:
            return overrides[key]
        return {"method": method}

    return call_fn


def test_all_ok_all_usable():
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn())
    assert usable_providers(matrix, METHOD_NAMES) == ["p1", "p2", "p3"]


def test_missing_method_not_usable():
    errors = {("p3", "eth_gasPrice"): RuntimeError("nope")}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(errors=errors))
    usable = usable_providers(matrix, METHOD_NAMES)
    assert "p3" not in usable
    assert usable == ["p1", "p2"]


def test_missing_method_key_not_usable():
    matrix = {
        "p1": {m: {"ok": True} for m in METHOD_NAMES},
        "p2": {m: {"ok": True} for m in METHOD_NAMES[:-1]},  # last method absent
    }
    assert usable_providers(matrix, METHOD_NAMES) == ["p1"]


def test_usable_requires_all_methods():
    matrix = {
        "p1": {m: {"ok": True} for m in METHOD_NAMES},
        "p2": {m: {"ok": (m != "eth_call")} for m in METHOD_NAMES},
    }
    assert usable_providers(matrix, METHOD_NAMES) == ["p1"]


def test_method_exception_isolated_matrix_complete():
    errors = {("p2", "eth_call"): RuntimeError("boom")}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(errors=errors))
    assert set(matrix) == {"p1", "p2", "p3"}
    for row in matrix.values():
        assert set(row) == set(METHOD_NAMES)
    assert matrix["p2"]["eth_call"]["ok"] is False
    assert matrix["p2"]["eth_call"]["error"] is not None
    assert matrix["p2"]["eth_call"]["result_digest"] is None
    for m in ("eth_chainId", "eth_blockNumber", "eth_gasPrice"):
        assert matrix["p2"][m]["ok"] is True


def test_provider_total_failure_isolated():
    errors = {("p2", m): RuntimeError("down") for m in METHOD_NAMES}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(errors=errors))
    assert all(v["ok"] is False for v in matrix["p2"].values())
    assert all(v["ok"] is True for v in matrix["p1"].values())
    assert usable_providers(matrix, METHOD_NAMES) == ["p1", "p3"]


def test_matrix_shape_3x4():
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn())
    assert len(matrix) == 3
    for row in matrix.values():
        assert len(row) == 4


def test_digest_is_16_hex_chars():
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn())
    d = matrix["p1"]["eth_chainId"]["result_digest"]
    assert isinstance(d, str) and len(d) == 16
    int(d, 16)  # must be valid hex


def test_digest_matches_spec():
    result = {"a": 1, "b": 2}
    overrides = {("p1", "eth_chainId"): result}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(overrides=overrides))
    expected = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    assert matrix["p1"]["eth_chainId"]["result_digest"] == expected


def test_latency_is_float():
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn())
    lat = matrix["p1"]["eth_chainId"]["latency_ms"]
    assert isinstance(lat, float) and lat >= 0.0


def test_disagreement_one_differs():
    overrides = {("p3", "eth_chainId"): {"value": "0xff"}}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(overrides=overrides))
    out = detect_disagreement(matrix, METHODS, consensus_methods=["eth_chainId"])
    assert len(out) == 1
    assert out[0]["method"] == "eth_chainId"
    assert set(out[0]["digests"]) == {"p1", "p2", "p3"}
    assert out[0]["digests"]["p1"] == out[0]["digests"]["p2"]
    assert out[0]["digests"]["p3"] != out[0]["digests"]["p1"]


def test_disagreement_all_same():
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn())
    out = detect_disagreement(
        matrix, METHODS, consensus_methods=["eth_chainId", "eth_blockNumber"]
    )
    assert out == []


def test_disagreement_ignores_failed_provider():
    errors = {("p3", "eth_chainId"): RuntimeError("down")}
    matrix = verify_provider_methods(PROVIDERS, METHODS, make_call_fn(errors=errors))
    out = detect_disagreement(matrix, METHODS, consensus_methods=["eth_chainId"])
    assert out == []


def test_backoff_cap_finite_no_overflow():
    pool = ProviderPool(PROVIDERS)
    now = time.monotonic()
    for _ in range(5000):
        pool.report_failure("p1", now)
    cu = pool.health()["p1"]["cooling_until"]
    assert isinstance(cu, float)
    assert math.isfinite(cu)
    assert pool.health()["p1"]["fails"] == 5000


def test_backoff_grows_exponentially_before_cap():
    pool = ProviderPool(PROVIDERS, cooldown_base=2.0)
    now = 1000.0
    pool.report_failure("p1", now)
    assert pool.health()["p1"]["cooling_until"] == now + 1.0  # 2**0
    pool.report_failure("p1", now)
    assert pool.health()["p1"]["cooling_until"] == now + 2.0  # 2**1
    pool.report_failure("p1", now)
    assert pool.health()["p1"]["cooling_until"] == now + 4.0  # 2**2


def test_backoff_capped_at_max_exponent():
    pool = ProviderPool(PROVIDERS, cooldown_base=2.0, max_backoff_exponent=5)
    now = 0.0
    for _ in range(100):
        pool.report_failure("p1", now)
    assert pool.health()["p1"]["cooling_until"] == now + 32.0  # capped at 2**5


def test_report_failure_increments():
    pool = ProviderPool(PROVIDERS)
    now = time.monotonic()
    pool.report_failure("p1", now)
    pool.report_failure("p1", now)
    assert pool.health()["p1"]["fails"] == 2


def test_success_resets_fails_and_pickable():
    pool = ProviderPool(PROVIDERS)
    pool.report_failure("p1", time.monotonic())
    assert pool.health()["p1"]["fails"] == 1
    pool.report_success("p1")
    assert pool.health()["p1"]["fails"] == 0
    assert pool.health()["p1"]["cooling_until"] == 0.0
    solo = ProviderPool([PROVIDERS[0]])
    solo.report_failure("p1", time.monotonic())
    assert solo.pick() is None  # cooling
    solo.report_success("p1")
    assert solo.pick()["name"] == "p1"  # immediately eligible


def test_all_cooling_returns_none():
    pool = ProviderPool(PROVIDERS)
    now = time.monotonic()
    for p in PROVIDERS:
        pool.report_failure(p["name"], now)
    assert pool.pick() is None


def test_round_robin_fairness():
    pool = ProviderPool(PROVIDERS)
    picks = [pool.pick()["name"] for _ in range(6)]
    assert picks.count("p1") == 2
    assert picks.count("p2") == 2
    assert picks.count("p3") == 2


def test_pick_skips_cooling_provider():
    pool = ProviderPool(PROVIDERS)
    pool.report_failure("p2", time.monotonic())  # p2 cooling ~1s
    seen = {pool.pick()["name"] for _ in range(6)}
    assert "p2" not in seen
    assert seen == {"p1", "p3"}


def test_pick_empty_pool_none():
    assert ProviderPool([]).pick() is None


def test_health_structure():
    pool = ProviderPool(PROVIDERS)
    h = pool.health()
    assert set(h) == {"p1", "p2", "p3"}
    for v in h.values():
        assert set(v) == {"fails", "cooling_until", "last_ok"}
        assert v["fails"] == 0
        assert v["last_ok"] is None


def test_live_readiness_1_blocked_single():
    assert live_readiness(1) == {
        "status": "BLOCKED", "reason": "SINGLE_PROVIDER", "usable_count": 1,
    }


def test_live_readiness_0_blocked_no():
    assert live_readiness(0) == {
        "status": "BLOCKED", "reason": "NO_PROVIDER", "usable_count": 0,
    }


def test_live_readiness_2_pass():
    assert live_readiness(2) == {"status": "PASS", "reason": None, "usable_count": 2}


def test_live_readiness_min_required_explicit():
    assert live_readiness(1, min_required=1)["status"] == "PASS"
    # default is 2 and is not lowered internally
    assert live_readiness(1)["status"] == "BLOCKED"


def test_default_clock_self_consistent():
    # No `now` passed anywhere: report_failure and pick both default to
    # time.monotonic(), so a single failure makes the provider cooling and
    # pick() must return None (the default clock is self-consistent).
    pool = ProviderPool([PROVIDERS[0]])
    pool.report_failure("p1")
    assert pool.pick() is None


def test_injected_clock_cooldown_release():
    # Same injected clock for report_failure and pick: cooldown releases
    # exactly `cooldown` seconds (2**0 = 1.0s) after the failure.
    pool = ProviderPool([PROVIDERS[0]])
    t0 = 1000.0
    pool.report_failure("p1", now=t0)  # cooling_until = t0 + 1.0
    assert pool.pick(now=t0 + 0.5) is None  # still cooling
    assert pool.pick(now=t0 + 1.0)["name"] == "p1"  # released


def test_wall_clock_injected_consistently_no_permanent_cooldown():
    # The round-1 bug was a clock MISMATCH: report_failure wrote a wall-clock
    # deadline that pick() compared against monotonic, so a time.time()-sized
    # value looked permanently cooling. Under the documented convention (one
    # injected clock for both calls), even a time.time()-magnitude value
    # releases after exactly `cooldown` seconds -- no permanent cooldown.
    pool = ProviderPool([PROVIDERS[0]])
    t0 = time.time()  # ~1.7e9, far larger than time.monotonic()
    pool.report_failure("p1", now=t0)  # cooling_until = t0 + 1.0
    assert pool.pick(now=t0 + 0.5) is None  # still cooling
    assert pool.pick(now=t0 + 1.0)["name"] == "p1"  # released, not permanent
