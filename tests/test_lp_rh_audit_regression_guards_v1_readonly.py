"""RH-02y regression guards for audit "需关注" items T09 and T45.

Neither item is a functional defect: the current behavior is correct, but
nothing stops a future edit from breaking it. These tests pin the behavior.

T09 (PRD §20): a web-page APR must not influence any decision path. The
decision functions never read an ``apr`` field, so injecting APR payloads
into a candidate must leave every result byte-for-byte identical.

T45 (PRD §20): in an atomic exit, a reverted swap means the remove is also
incomplete; only after an independent re-check (``atomic=False``) may the
position be treated as remove-only (``REMOVED_RISKY_INVENTORY``).

Read-only: no network, no wallet, no chain state. No implementation file is
modified; this package only adds tests.
"""
import re
import sys

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts.lp_rh_meme_audit_v1_readonly import exit_state_machine
from scripts.lp_rh_pool_probe_v1_readonly import (
    dispatch_protocol, probe_v3_pool, probe_v4_pool,
)

REPO = '/opt/lpbot/lp-bot-v3-origin-check'

# --- shared fixtures -------------------------------------------------------
# Minimal V3 candidate (20-byte pool, no pool_id) and V4 candidate
# (32-byte pool_id, no pool). Neither carries any APR-like field.
V3_CAND = {
    "pool": "0x" + "11" * 20,
    "factory": "0x" + "22" * 20,
}
V4_CAND = {
    "pool_manager": "0x" + "33" * 20,
    "pool_id": "0x" + "44" * 32,
    "currency0": "0x" + "55" * 20,
    "currency1": "0x" + "66" * 20,
    "fee": 10000,
    "tick_spacing": 60,
    "hooks": "0x" + "00" * 32,
}

# APR payloads that must be inert: the decision path never reads them.
APR_BLOB = {"apr": 999.0, "APR": "999%", "apy": 1e9, "web_apr": 42}


def _fake_rpc(method, params):
    """Deterministic offline rpc: every call is a JSON-RPC error, so the
    probes fail-closed at the first call and return a stable dict. No
    network, no time-dependent fields."""
    return {"jsonrpc": "2.0", "id": 0,
            "error": {"code": -32000, "message": "fixture: offline"}}


def _with_apr(base, extra):
    c = dict(base)
    c.update(extra)
    return c


def _assert_key_equal(a, b, label):
    """Assert two probe-output dicts are equal key-by-key. No volatile
    fields (timestamps / random) exist in these outputs, so no key is
    excluded; every key is compared."""
    assert set(a) == set(b), f"{label}: key sets differ: {set(a) ^ set(b)}"
    for k in a:
        assert a[k] == b[k], f"{label}: key {k!r} differs: {a[k]!r} != {b[k]!r}"


def _source_text(name):
    with open(f"{REPO}/scripts/{name}", "r", encoding="utf-8") as fh:
        return fh.read()


# --- T09: web-page APR must not influence any result ----------------------

def test_dispatch_protocol_apr_invariant():
    base = dispatch_protocol(dict(V3_CAND))
    injected = dispatch_protocol(_with_apr(V3_CAND, APR_BLOB))
    assert base == injected
    assert base == "v3"


def test_probe_v3_pool_apr_invariant():
    a = probe_v3_pool(dict(V3_CAND), _fake_rpc)
    b = probe_v3_pool(_with_apr(V3_CAND, APR_BLOB), _fake_rpc)
    _assert_key_equal(a, b, "probe_v3_pool")


def test_probe_v4_pool_apr_invariant():
    a = probe_v4_pool(dict(V4_CAND), _fake_rpc)
    b = probe_v4_pool(_with_apr(V4_CAND, APR_BLOB), _fake_rpc)
    _assert_key_equal(a, b, "probe_v4_pool")


def test_probe_v3_pool_apr_negative_inert():
    a = probe_v3_pool(dict(V3_CAND), _fake_rpc)
    b = probe_v3_pool(_with_apr(V3_CAND, {"apr": -1.0}), _fake_rpc)
    _assert_key_equal(a, b, "probe_v3_pool(apr=-1.0)")


def test_probe_v3_pool_apr_none_inert():
    a = probe_v3_pool(dict(V3_CAND), _fake_rpc)
    b = probe_v3_pool(_with_apr(V3_CAND, {"apr": None}), _fake_rpc)
    _assert_key_equal(a, b, "probe_v3_pool(apr=None)")


def test_probe_v3_pool_apr_long_string_inert():
    a = probe_v3_pool(dict(V3_CAND), _fake_rpc)
    b = probe_v3_pool(_with_apr(V3_CAND, {"apr": "A" * 10000}), _fake_rpc)
    _assert_key_equal(a, b, "probe_v3_pool(apr=long)")


def test_source_no_apr_pool_probe():
    text = _source_text("lp_rh_pool_probe_v1_readonly.py")
    m = re.search(r"\bapr\b", text, re.IGNORECASE)
    assert m is None, "PRD T09：网页 APR 不得进入判定路径 (lp_rh_pool_probe_v1_readonly.py)"


def test_source_no_apr_capabilities():
    text = _source_text("lp_rh_capabilities_v1_readonly.py")
    m = re.search(r"\bapr\b", text, re.IGNORECASE)
    assert m is None, "PRD T09：网页 APR 不得进入判定路径 (lp_rh_capabilities_v1_readonly.py)"


def test_source_no_apr_registry():
    text = _source_text("lp_rh_registry_v1_readonly.py")
    m = re.search(r"\bapr\b", text, re.IGNORECASE)
    assert m is None, "PRD T09：网页 APR 不得进入判定路径 (lp_rh_registry_v1_readonly.py)"


# --- T45: atomic rollback must not be treated as remove-only --------------

def test_atomic_reverted_remove_not_effective():
    status, info = exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)
    assert status == "ATOMIC_EXIT_REVERTED"
    assert info["remove_effective"] is False


def test_atomic_reverted_is_not_remove_only():
    status, _ = exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)
    assert status != "REMOVED_RISKY_INVENTORY"


def test_independent_recheck_yields_remove_only():
    s_atomic, _ = exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)
    s_recheck, _ = exit_state_machine(remove_ok=True, swap_ok=False, atomic=False)
    assert s_atomic != s_recheck
    assert s_recheck == "REMOVED_RISKY_INVENTORY"


def test_atomic_reverted_no_cap_released():
    _, info = exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)
    assert info.get("asset_cap_released") is not True


def test_recheck_residual_risk_and_cap_held():
    _, info = exit_state_machine(remove_ok=True, swap_ok=False, atomic=False)
    assert info["residual_risk"] is True
    assert info["asset_cap_released"] is False


def test_atomic_reverted_remove_ok_ignored():
    status, _ = exit_state_machine(remove_ok=False, swap_ok=False, atomic=True)
    assert status == "ATOMIC_EXIT_REVERTED"


def test_swap_none_atomic_not_reverted():
    status, _ = exit_state_machine(remove_ok=True, swap_ok=None, atomic=True)
    assert status != "ATOMIC_EXIT_REVERTED"


def test_swap_none_unknown_reconcile():
    status, info = exit_state_machine(remove_ok=True, swap_ok=None, atomic=True)
    assert status == "EXIT_UNKNOWN_RECONCILE_REQUIRED"
    assert info["asset_cap_released"] is False


def test_success_path_regression():
    status, info = exit_state_machine(remove_ok=True, swap_ok=True, atomic=True)
    assert status == "CLOSED_RECONCILED"
    assert info["asset_cap_released"] is True
