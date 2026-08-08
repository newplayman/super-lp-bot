"""Pure tests for the rotating multi-endpoint RPC pool (no network).

Transport (`post`) and clock (`now`/`sleep`) are injected, so every test is
deterministic and offline.
"""
import pytest

from scripts.lp_rpc_pool_v1_readonly import RpcPool, CHAINS, _build_request

GETLOGS = "eth_getLogs"
CHEAP = "eth_blockNumber"


# --- transport doubles -----------------------------------------------------

def ok_recorder():
    """post() that always succeeds and records (url, method) calls."""
    calls = []

    def post(url, method, params, timeout=20):
        calls.append((url, method))
        return {"result": "0x1"}

    return post, calls


def fail_for(bad_urls):
    """post() that raises a transport error for `bad_urls`, else succeeds."""
    calls = []

    def post(url, method, params, timeout=20):
        calls.append((url, method))
        if url in bad_urls:
            raise OSError("HTTP Error 403: Forbidden")
        return {"result": "0xabc"}

    return post, calls


class Clock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, _secs):
        pass


# --- registry --------------------------------------------------------------

def test_base_chain_has_verified_getlogs_endpoints():
    eps = CHAINS["base"]["endpoints"]
    getlogs = {e["url"] for e in eps if e["getlogs"]}
    assert "https://mainnet.base.org" in getlogs
    assert "https://base.drpc.org" in getlogs
    assert "https://base.lava.build" in getlogs
    # cheap-only endpoints exist and are NOT flagged getlogs
    cheap_only = {e["url"] for e in eps if not e["getlogs"]}
    assert "https://1rpc.io/base" in cheap_only
    assert len(eps) >= 7


def test_multichain_registry_is_extensible():
    # the registry is keyed by chain so other chains can be added
    assert "base" in CHAINS
    for chain, cfg in CHAINS.items():
        assert "endpoints" in cfg and cfg["endpoints"]
        for e in cfg["endpoints"]:
            assert "url" in e and "getlogs" in e


# --- method-aware endpoint selection --------------------------------------

def test_getlogs_only_routes_to_getlogs_capable_endpoints():
    post, calls = ok_recorder()
    pool = RpcPool("base", post=post, clock=Clock())
    capable = {e["url"] for e in CHAINS["base"]["endpoints"] if e["getlogs"]}
    for _ in range(30):
        pool.call(GETLOGS, [{}])
    used = {u for (u, m) in calls}
    assert used <= capable          # never hit a non-getlogs endpoint
    assert len(used) >= 2           # actually spread across several


def test_cheap_calls_use_the_full_pool_including_cheap_only():
    post, calls = ok_recorder()
    pool = RpcPool("base", post=post, clock=Clock())
    cheap_only = {e["url"] for e in CHAINS["base"]["endpoints"] if not e["getlogs"]}
    for _ in range(40):
        pool.call(CHEAP, [])
    used = {u for (u, m) in calls}
    assert used & cheap_only        # cheap-only endpoints are actually used


# --- rotation / load distribution -----------------------------------------

def test_rotation_distributes_consecutive_calls():
    post, calls = ok_recorder()
    pool = RpcPool("base", post=post, clock=Clock())
    # two consecutive successful calls should not hammer the same endpoint
    pool.call(CHEAP, [])
    pool.call(CHEAP, [])
    assert calls[0][0] != calls[1][0]


# --- health / backoff ------------------------------------------------------

def test_failed_endpoint_is_skipped_and_next_succeeds():
    all_eps = [e["url"] for e in CHAINS["base"]["endpoints"]]
    bad = {all_eps[0]}
    post, calls = fail_for(bad)
    pool = RpcPool("base", post=post, clock=Clock())
    res = pool.call(CHEAP, [])      # first pick may fail, must fall through
    assert res == "0xabc"
    assert calls[-1][0] not in bad  # the call that returned was a healthy one


def test_failed_endpoint_in_cooldown_is_not_retried():
    all_eps = [e["url"] for e in CHAINS["base"]["endpoints"]]
    bad = {all_eps[0]}
    post, calls = fail_for(bad)
    clock = Clock()
    pool = RpcPool("base", post=post, clock=clock)
    pool.call(CHEAP, [])            # trips the bad endpoint into cooldown
    calls.clear()
    for _ in range(20):
        pool.call(CHEAP, [])
    assert all(u not in bad for (u, m) in calls)   # cooled-down, never retried


def test_cooldown_expires_and_endpoint_is_reused():
    all_eps = [e["url"] for e in CHAINS["base"]["endpoints"]]
    bad = {all_eps[0]}
    calls = []

    def post(url, method, params, timeout=20):
        calls.append((url, method))
        # only fails on the very first contact, then "recovers"
        if url in bad and len(calls) == 1:
            raise OSError("timeout")
        return {"result": "0x2"}

    clock = Clock()
    pool = RpcPool("base", post=post, clock=clock)
    pool.call(CHEAP, [])
    clock.t += 10_000              # well past any cooldown
    calls.clear()
    for _ in range(40):
        pool.call(CHEAP, [])
    assert any(u in bad for (u, m) in calls)   # endpoint healed and is used again


def test_backoff_grows_with_consecutive_failures():
    url = CHAINS["base"]["endpoints"][0]["url"]
    clock = Clock()
    pool = RpcPool("base", post=lambda *a, **k: {"result": "x"}, clock=clock)
    pool._penalize(url)
    first = pool._cooldown_until[url] - clock.now()
    pool._penalize(url)
    second = pool._cooldown_until[url] - clock.now()
    assert second > first


def test_all_endpoints_failing_raises_not_loops():
    post = lambda url, method, params, timeout=20: (_ for _ in ()).throw(OSError("403"))
    pool = RpcPool("base", post=post, clock=Clock())
    with pytest.raises(RuntimeError):
        pool.call(CHEAP, [])


def test_json_rpc_error_response_falls_through_to_next_endpoint():
    all_eps = [e["url"] for e in CHAINS["base"]["endpoints"]]
    bad = {all_eps[0]}
    calls = []

    def post(url, method, params, timeout=20):
        calls.append((url, method))
        if url in bad:
            return {"error": {"code": -32005, "message": "rate limited"}}
        return {"result": "0xfee"}

    pool = RpcPool("base", post=post, clock=Clock())
    assert pool.call(CHEAP, []) == "0xfee"     # error response is not returned as success


def test_call_unwraps_result_value():
    pool = RpcPool("base", post=lambda *a, **k: {"result": "0xdeadbeef"}, clock=Clock())
    assert pool.call(CHEAP, []) == "0xdeadbeef"


def test_default_request_sets_non_urllib_user_agent():
    # public RPCs 403 the default Python-urllib UA; we must send a real one
    req = _build_request("https://example.org", "eth_blockNumber", [])
    ua = req.get_header("User-agent")     # urllib title-cases header keys
    assert ua and "urllib" not in ua.lower()
    assert req.get_header("Content-type") == "application/json"
