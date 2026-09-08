import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import hashlib
import json
import sqlite3

from scripts.lp_rh_provider_health_recorder_v1_readonly import (
    CAPABILITIES,
    PROBE_TO_RPC,
    CONSENSUS_METHODS,
    JsonRpcError,
    SCHEMA,
    _build_probes,
    _fetch_head,
    _probe_error_structure,
    run_round,
)

PROVIDERS = [
    {"name": "p1", "url": "http://p1"},
    {"name": "p2", "url": "http://p2"},
    {"name": "p3", "url": "http://p3"},
    {"name": "p4", "url": "http://p4"},
]
URL_TO_NAME = {p["url"]: p["name"] for p in PROVIDERS}
CAPS = list(CAPABILITIES)


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def make_call_fn(overrides=None, errors=None, head="0x100"):
    """Offline fake call_fn for the recorder.

    The recorder's ``call_fn`` is keyed on ``(provider_name, probe_name)``
    where probe_name is a capability (or the special ``"head"``). By default
    every provider returns the same value for a given probe (so digests agree),
    ``head`` returns a hex block number, and ``error_structure`` raises a
    structured JsonRpcError (the ok case for that inverted capability).
    ``overrides``/``errors`` key on ``(provider_name, probe_name)``.
    """
    overrides = overrides or {}
    errors = errors or {}

    def call_fn(url, probe, params):
        name = URL_TO_NAME[url]
        key = (name, probe)
        if key in errors:
            raise errors[key]
        if key in overrides:
            return overrides[key]
        if probe == "head":
            return head
        if probe == "chain_id":
            return "0x1237"  # 4663: the expected chain, so the default is ok
        if probe == "error_structure":
            raise JsonRpcError(-32601, "method not found")
        # Provider-independent value so digests agree across providers by
        # default (a per-provider value would read as a false disagreement).
        return {"probe": probe}

    return call_fn


def _cap(conn, sample_time, provider, capability, col="ok"):
    return conn.execute(
        "select %s from rh_provider_capability where sample_time=? "
        "and provider=? and capability=?" % col,
        (sample_time, provider, capability),
    ).fetchone()[0]


# --- constants -------------------------------------------------------------

def test_capabilities_eight_fixed_order():
    assert CAPABILITIES == [
        "chain_id", "block_hash_consistency", "historical_read",
        "log_range_1k", "log_range_10k", "eth_call", "gas_estimate",
        "error_structure",
    ]


def test_consensus_methods_exclude_head_include_chain_id():
    # eth_blockNumber is the ONLY deliberately excluded consensus method: each
    # provider reports its own chain head, so comparing it would misreport
    # normal sync lag as SOURCE_DISAGREEMENT. chain_id is a constant (4663)
    # and MUST be compared across providers.
    assert "head" not in CONSENSUS_METHODS
    assert "eth_blockNumber" not in CONSENSUS_METHODS
    assert CONSENSUS_METHODS == ["chain_id", "block_hash_consistency",
                                 "eth_call"]


# --- _build_probes ---------------------------------------------------------

def test_build_probes_seven_in_order():
    probes = _build_probes(head=0x100, pinned_block=0x100 - 60)
    assert [p["method"] for p in probes] == [
        "chain_id", "block_hash_consistency", "historical_read",
        "log_range_1k", "log_range_10k", "eth_call", "gas_estimate",
    ]


def test_build_probes_pinned_block_used():
    head, pinned = 0x100, 0x100 - 60
    probes = _build_probes(head=head, pinned_block=pinned)
    bhc = next(p for p in probes if p["method"] == "block_hash_consistency")
    assert bhc["params"][0] == hex(pinned)
    ec = next(p for p in probes if p["method"] == "eth_call")
    assert ec["params"][1] == hex(pinned)
    # historical_read targets a far-older block, not the pinned one
    hist = next(p for p in probes if p["method"] == "historical_read")
    assert hist["params"][1] == hex(head - 100000)


# --- _fetch_head -----------------------------------------------------------

def test_fetch_head_first_provider_that_answers():
    def call_fn(url, probe, params):
        if url == "http://p1":
            raise RuntimeError("down")
        return "0x2a"
    assert _fetch_head(PROVIDERS, call_fn) == 0x2a


def test_fetch_head_none_if_all_fail():
    def call_fn(url, probe, params):
        raise RuntimeError("down")
    assert _fetch_head(PROVIDERS, call_fn) is None


# --- JsonRpcError ----------------------------------------------------------

def test_jsonrpc_error_structure():
    e = JsonRpcError(-32601, "method not found", {"x": 1})
    assert e.code == -32601
    assert e.message == "method not found"
    assert e.data == {"x": 1}
    assert "method not found" in str(e)


# --- _probe_error_structure ------------------------------------------------

def test_probe_error_structure_ok_on_jsonrpc_error():
    def call_fn(url, probe, params):
        raise JsonRpcError(-32601, "m")
    rec = _probe_error_structure("http://p1", call_fn)
    assert rec["ok"] is True
    assert isinstance(rec["latency_ms"], float)
    assert rec["result_digest"] is not None
    assert rec["error"] is None


def test_probe_error_structure_not_ok_on_http_error():
    def call_fn(url, probe, params):
        raise RuntimeError("HTTP 500")
    rec = _probe_error_structure("http://p1", call_fn)
    assert rec["ok"] is False
    assert rec["latency_ms"] is None  # failure rows: NULL, never 0
    assert rec["error"] is not None


def test_probe_error_structure_not_ok_on_result():
    def call_fn(url, probe, params):
        return {"unexpected": "result"}
    rec = _probe_error_structure("http://p1", call_fn)
    assert rec["ok"] is False
    assert "expected JSON-RPC error" in rec["error"]


# --- run_round: happy path -------------------------------------------------

def test_run_round_all_ok_writes_8_rows_per_provider():
    conn = make_db()
    summary = run_round(conn, PROVIDERS, make_call_fn(), "t1")
    rows = conn.execute(
        "select provider, capability from rh_provider_capability "
        "where sample_time='t1' order by provider, capability").fetchall()
    assert len(rows) == 4 * 8
    for prov in PROVIDERS:
        caps = {r[1] for r in rows if r[0] == prov["name"]}
        assert caps == set(CAPS)  # exactly the 8 capabilities, one row each
    assert summary["usable_count"] == 4
    assert summary["live_gate_status"] == "PASS"


def test_run_round_rollup_row_fields():
    conn = make_db()
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    row = conn.execute(
        "select usable_count, usable_providers_json, live_gate_status, "
        "live_gate_reason, head_block, pinned_block "
        "from rh_provider_rollup where sample_time='t1'").fetchone()
    assert row[0] == 4
    assert json.loads(row[1]) == ["p1", "p2", "p3", "p4"]
    assert row[2] == "PASS"
    assert row[3] is None
    assert row[4] == 0x100          # head
    assert row[5] == 0x100 - 60     # pinned


def test_success_row_latency_is_float():
    conn = make_db()
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    assert isinstance(_cap(conn, "t1", "p1", "chain_id", "latency_ms"), float)
    assert _cap(conn, "t1", "p1", "chain_id") == 1


def test_capability_digest_matches_spec():
    conn = make_db()
    overrides = {("p1", "chain_id"): {"chainId": "0x1267"}}
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    got = _cap(conn, "t1", "p1", "chain_id", "result_digest")
    expected = hashlib.sha256(
        json.dumps({"chainId": "0x1267"}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    assert got == expected


# --- run_round: failure isolation ------------------------------------------

def test_failure_row_latency_is_null():
    conn = make_db()
    errors = {("p2", "eth_call"): RuntimeError("boom")}
    run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    assert _cap(conn, "t1", "p2", "eth_call") == 0
    assert _cap(conn, "t1", "p2", "eth_call", "latency_ms") is None
    assert _cap(conn, "t1", "p2", "eth_call", "error") is not None
    # the other capabilities of p2 are unaffected
    assert _cap(conn, "t1", "p2", "chain_id") == 1


def test_one_provider_total_failure_isolated():
    conn = make_db()
    errors = {("p2", c): RuntimeError("down") for c in CAPS + ["head"]}
    summary = run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    p2 = conn.execute(
        "select ok from rh_provider_capability "
        "where sample_time='t1' and provider='p2'").fetchall()
    assert len(p2) == 8 and all(r[0] == 0 for r in p2)
    p1 = conn.execute(
        "select ok from rh_provider_capability "
        "where sample_time='t1' and provider='p1'").fetchall()
    assert all(r[0] == 1 for r in p1)
    assert summary["usable_count"] == 3


def test_usable_fail_closed_one_cap_missing():
    conn = make_db()
    errors = {("p4", "gas_estimate"): RuntimeError("no gas")}
    summary = run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    # p4 fails exactly one capability -> unusable (fail-closed over ALL caps)
    assert summary["usable_count"] == 3


# --- run_round: error_structure through the round --------------------------

def test_error_structure_ok_by_default():
    conn = make_db()
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    assert _cap(conn, "t1", "p1", "error_structure") == 1


def test_error_structure_not_ok_on_http_error():
    conn = make_db()
    errors = {("p1", "error_structure"): RuntimeError("HTTP 500")}
    run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    assert _cap(conn, "t1", "p1", "error_structure") == 0


def test_error_structure_not_ok_on_result():
    conn = make_db()
    overrides = {("p1", "error_structure"): {"result": "unexpected"}}
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    assert _cap(conn, "t1", "p1", "error_structure") == 0
    assert "expected JSON-RPC error" in _cap(
        conn, "t1", "p1", "error_structure", "error")


# --- run_round: consensus disagreement -------------------------------------

def test_run_round_detects_consensus_disagreement():
    conn = make_db()
    overrides = {("p3", "block_hash_consistency"): {"hash": "0xdead"}}
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert len(dis) == 1
    assert dis[0]["method"] == "block_hash_consistency"
    assert set(dis[0]["digests"]) == {"p1", "p2", "p3", "p4"}
    assert dis[0]["digests"]["p3"] != dis[0]["digests"]["p1"]


def test_run_round_no_disagreement_when_all_agree():
    conn = make_db()
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert dis == []


def test_run_round_disagreement_ignores_failed_provider():
    conn = make_db()
    # p4's consensus method fails -> omitted from the comparison, no false
    # disagreement among the providers that did answer.
    errors = {("p4", "block_hash_consistency"): RuntimeError("down")}
    run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert dis == []


# --- run_round: no head available ------------------------------------------

def test_no_head_still_writes_8_rows_per_provider():
    conn = make_db()
    errors = {("p%d" % i, "head"): RuntimeError("down") for i in (1, 2, 3, 4)}
    summary = run_round(conn, PROVIDERS, make_call_fn(errors=errors), "t1")
    n = conn.execute(
        "select count(*) from rh_provider_capability "
        "where sample_time='t1'").fetchone()[0]
    assert n == 4 * 8  # never fewer than 8 rows per provider
    assert summary["head_block"] is None
    assert summary["pinned_block"] is None
    # every pinned-block capability fails when there is no head
    for prov in PROVIDERS:
        for cap in ("block_hash_consistency", "historical_read",
                    "log_range_1k", "log_range_10k", "eth_call",
                    "gas_estimate"):
            assert _cap(conn, "t1", prov["name"], cap) == 0
    # no usable provider -> gate BLOCKED
    assert summary["usable_count"] == 0
    assert summary["live_gate_status"] == "BLOCKED"


# --- idempotency -----------------------------------------------------------

def test_same_sample_time_replaces_not_duplicates():
    conn = make_db()
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    run_round(conn, PROVIDERS, make_call_fn(), "t1")
    n = conn.execute(
        "select count(*) from rh_provider_capability "
        "where sample_time='t1'").fetchone()[0]
    assert n == 4 * 8
    nr = conn.execute(
        "select count(*) from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0]
    assert nr == 1


# --- chain_id value validation (round 2: FAIL-1 / FAIL-2) ------------------

def test_chain_id_wrong_chain_not_usable():
    # Reproduces the main-brain control: a Base (8453) endpoint answering
    # every other capability correctly must NOT count as usable.
    conn = make_db()
    overrides = {("p3", "chain_id"): "0x2105"}  # 8453
    summary = run_round(conn, PROVIDERS, make_call_fn(overrides=overrides),
                        "t1")
    assert _cap(conn, "t1", "p3", "chain_id") == 0
    err = _cap(conn, "t1", "p3", "chain_id", "error")
    assert "8453" in err and "4663" in err
    usable = json.loads(conn.execute(
        "select usable_providers_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert "p3" not in usable
    assert summary["usable_count"] == 3


def test_chain_id_all_correct_no_disagreement():
    conn = make_db()
    overrides = {(p["name"], "chain_id"): "0x1237" for p in PROVIDERS}
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    for p in PROVIDERS:
        assert _cap(conn, "t1", p["name"], "chain_id") == 1
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert dis == []


def test_chain_id_disagreement_detected():
    conn = make_db()
    overrides = {
        ("p1", "chain_id"): "0x1237",
        ("p2", "chain_id"): "0x1237",
        ("p3", "chain_id"): "0x2105",
        ("p4", "chain_id"): "0x2106",
    }
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert len(dis) == 1
    assert dis[0]["method"] == "chain_id"
    assert set(dis[0]["digests"]) == {"p1", "p2", "p3", "p4"}
    assert len(set(dis[0]["digests"].values())) == 3  # 3 distinct chain ids


def test_head_block_differences_not_disagreement():
    # Per-provider head values differ, but eth_blockNumber is NOT a consensus
    # method, so no disagreement may be recorded.
    conn = make_db()
    overrides = {
        ("p1", "head"): "0x100",
        ("p2", "head"): "0x200",
        ("p3", "head"): "0x300",
        ("p4", "head"): "0x400",
    }
    run_round(conn, PROVIDERS, make_call_fn(overrides=overrides), "t1")
    dis = json.loads(conn.execute(
        "select disagreements_json from rh_provider_rollup "
        "where sample_time='t1'").fetchone()[0])
    assert dis == []
    assert "head" not in CONSENSUS_METHODS
    assert "eth_blockNumber" not in CONSENSUS_METHODS


def test_main_once_returns_zero(tmp_path, monkeypatch):
    import scripts.lp_rh_provider_health_recorder_v1_readonly as rec
    monkeypatch.setattr(rec, "PROVIDERS", PROVIDERS)
    monkeypatch.setattr(rec, "_default_call_fn", make_call_fn())
    db = tmp_path / "provider_health.db"
    assert rec.main(["--db", str(db), "--once"]) == 0
    assert db.exists()


# Real JSON-RPC method names, per the Ethereum JSON-RPC spec.  The one exception
# is the deliberately nonexistent probe used to test error structure.
REAL_RPC_METHODS = {
    "eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_getBlockByHash",
    "eth_call", "eth_getLogs", "eth_estimateGas", "eth_gasPrice", "eth_getBalance",
    "eth_getCode", "eth_getStorageAt", "eth_getTransactionByHash",
    "eth_getTransactionReceipt", "net_version", "web3_clientVersion",
}


def test_every_probe_uses_a_real_rpc_method_name():
    """A wrong method name passes every mocked test and fails every real call.

    Shipped as "eth_getBlock", which is not a JSON-RPC method.  Live, that made
    block_hash_consistency fail for all four providers at once and drove
    usable_count to 0 -- an entirely self-inflicted "no provider is usable"
    verdict.  Nothing in the suite could catch it because the fake call_fn never
    looks at the method name, so the name itself is asserted here.
    """
    for capability, method in PROBE_TO_RPC.items():
        if capability == "error_structure":
            assert method not in REAL_RPC_METHODS, (
                "error_structure must call a method that does not exist")
            continue
        assert method in REAL_RPC_METHODS, (
            f"{capability} maps to {method!r}, which is not a JSON-RPC method")


def test_block_hash_consistency_is_get_block_by_number():
    assert PROBE_TO_RPC["block_hash_consistency"] == "eth_getBlockByNumber"
