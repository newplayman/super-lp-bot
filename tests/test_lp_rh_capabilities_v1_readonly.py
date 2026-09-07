"""Paired tests for scripts/lp_rh_capabilities_v1_readonly.py (offline only).

Every provider probe is driven by an injected fake ``rpc`` callable or the
synthetic fixtures under tests/fixtures/rh/synthetic/; no network access.
Covers T01 (chain identity gate), T11/T13 (provider independence), T12
(a JSON-RPC error must never become a 0 result) and the capability matrix
contract (simulate/unsigned_build/broadcast/reconcile stay UNVERIFIED; V4 is
all UNSUPPORTED without a state view; every entry carries evidence +
expires_at).
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import lp_rh_capabilities_v1_readonly as caps

FIXTURES = Path(__file__).parent / "fixtures" / "rh" / "synthetic"
CHAIN_ID_HEX = "0x1237"  # 4663


def _probe(**kw):
    base = {"url": "https://one.example.com/rpc"}
    base.update(kw)
    return caps.ProviderProbe(**base)


def _fixture(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --- T01: chain identity gate -------------------------------------------------
def test_chain_identity_gate_ok_mismatch_unknown():
    assert caps.chain_identity_gate(_probe(chain_id_hex="0x1237")) == "CHAIN_ID_OK"
    assert caps.chain_identity_gate(_probe(chain_id_hex="0xb626")) == "CHAIN_ID_MISMATCH"
    assert caps.chain_identity_gate(_probe(chain_id_hex="0x1")) == "CHAIN_ID_MISMATCH"
    assert caps.chain_identity_gate(_probe(chain_id_hex=None)) == "CHAIN_ID_UNKNOWN"


# --- T12: JSON-RPC error must not be treated as a 0 result ---------------------
def test_probe_provider_jsonrpc_error_kept_and_block_number_none():
    def rpc(method, params):
        return {"jsonrpc": "2.0", "id": 1,
                "error": {"code": -32603, "message": "boom blockNumber failed"}}
    probe = caps.probe_provider("https://one.example.com/rpc", rpc=rpc)
    assert probe.error is not None
    assert "boom blockNumber failed" in probe.error
    assert probe.block_number is None  # must NOT be coerced to 0
    assert probe.chain_id_hex is None


def test_probe_provider_fixture_error_stops_at_chain_id():
    probe = caps.probe_provider(
        "offline", rpc=caps._fixture_rpc(_fixture("provider_probe_error.json")))
    assert probe.error is not None
    assert "boom chainId read failed" in probe.error
    assert probe.block_number is None
    assert probe.chain_id_hex is None


def test_probe_provider_fixture_ok_full_probe():
    probe = caps.probe_provider(
        "offline", rpc=caps._fixture_rpc(_fixture("provider_probe_ok.json")))
    assert probe.error is None
    assert probe.chain_id_hex == "0x1237"
    assert probe.block_number == 0x1234
    assert probe.block_hash == "0xblockhashaaaa"
    assert probe.client_version == "Geth/v1.13.0"
    assert probe.supports_eth_call is True
    assert probe.supports_get_logs is True
    assert probe.supports_estimate_gas is True
    assert caps.chain_identity_gate(probe) == "CHAIN_ID_OK"


# --- T13 / T11: provider independence ------------------------------------------
def test_provider_independence_same_backend_suspected():
    a = _probe(url="https://rpc1.chain.example.com", client_version="Geth/v1.13.0",
               block_hash="0xabc", block_number=100)
    b = _probe(url="https://rpc2.chain.example.com", client_version="Geth/v1.13.0",
               block_hash="0xabc", block_number=100)
    res = caps.provider_independence([a, b])
    assert res["independent"] is False
    assert res["reason"] == "SAME_BACKEND_SUSPECTED"


def test_provider_independence_block_hash_divergence():
    a = _probe(url="https://rpc1.chain.example.com", client_version="Geth/v1.13.0",
               block_hash="0xaaa", block_number=100)
    b = _probe(url="https://rpc2.chain.example.com", client_version="Geth/v1.13.0",
               block_hash="0xbbb", block_number=100)
    res = caps.provider_independence([a, b])
    assert res["independent"] is None
    assert res["reason"] == "BLOCK_HASH_DIVERGENCE"


def test_provider_independence_distinct_backends_height_within_two():
    a = _probe(url="https://one.example.com", block_hash="0xaaa", block_number=100)
    b = _probe(url="https://two.other.net", block_hash="0xbbb", block_number=102)
    res = caps.provider_independence([a, b])
    assert res["independent"] is True
    assert res["reason"] == "DISTINCT_BACKENDS"


# --- capability matrix -----------------------------------------------------------
def _ok_probe():
    return _probe(chain_id_hex=CHAIN_ID_HEX, block_number=100, block_hash="0xabc",
                  client_version="Geth/v1.13.0", supports_eth_call=True,
                  supports_get_logs=True, fetched_at="2026-09-07T00:00:00Z")


def test_capability_matrix_execution_keys_stay_unverified():
    matrix = caps.build_capability_matrix([_ok_probe()], {"v4_state_view_address": None})
    v3 = matrix["uniswap_v3@4663"]
    assert v3["discovery"]["status"] == "VERIFIED"
    assert v3["state_read"]["status"] == "VERIFIED"
    assert v3["history_read"]["status"] == "VERIFIED"
    for key in ("simulate", "unsigned_build", "broadcast", "reconcile"):
        assert v3[key]["status"] == "UNVERIFIED"
    for key in caps.CAPABILITY_KEYS:
        entry = v3[key]
        assert entry["evidence"] == {
            "url": "https://one.example.com/rpc", "block_number": 100}
        assert entry["expires_at"] == "2026-09-08T00:00:00Z"


def test_capability_matrix_v4_all_unsupported_without_state_view():
    matrix = caps.build_capability_matrix([_ok_probe()], {"v4_state_view_address": None})
    v4 = matrix["uniswap_v4@4663"]
    assert set(v4) == set(caps.CAPABILITY_KEYS)
    for key in caps.CAPABILITY_KEYS:
        assert v4[key]["status"] == "UNSUPPORTED"


def test_capability_matrix_v4_supported_with_state_view():
    flags = {"v4_state_view_address": "0x" + "11" * 20}
    matrix = caps.build_capability_matrix([_ok_probe()], flags)
    v4 = matrix["uniswap_v4@4663"]
    assert v4["discovery"]["status"] == "VERIFIED"
    assert v4["simulate"]["status"] == "UNVERIFIED"


# --- main() -----------------------------------------------------------------------
def test_main_no_provider_configured_exit_zero(monkeypatch, capsys):
    monkeypatch.delenv("RH_RPC_PRIMARY", raising=False)
    monkeypatch.delenv("RH_RPC_SECONDARY", raising=False)
    rc = caps.main([])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "NO_PROVIDER_CONFIGURED" in out["notes"]
    assert out["probes"] == []
    assert out["independence"]["reason"] == "INSUFFICIENT_PROVIDERS"
