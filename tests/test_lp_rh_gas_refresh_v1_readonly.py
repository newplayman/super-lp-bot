"""Tests for lp_rh_gas_refresh_v1_readonly (offline: fake rpc_fn + tmp JSON)."""
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts.lp_rh_gas_refresh_v1_readonly import (  # noqa: E402
    apply_to_pool_meta, collect_gas_inputs, compute_refresh, main,
)

GAS_PRICE_WEI = 232188000
NATIVE = "2484"
BLOCK_NUM = "0x1234"
EXPECTED = Decimal("0.4614039936")


def _env(result):
    return {"jsonrpc": "2.0", "id": 1, "result": result, "error": None}


def _receipts(n=8):
    return [{"gasUsed": "0x186a0", "effectiveGasPrice": "0x0debe0"} for _ in range(n)]


def make_rpc(block=None, gas_exc=None, gas_result="232188000"):
    default_block = {"number": BLOCK_NUM, "transactions": _receipts(8)}

    def rpc(method, params):
        if method == "eth_gasPrice":
            if gas_exc is not None:
                raise gas_exc
            return _env(gas_result)
        if method == "eth_getBlockByNumber":
            return _env(block if block is not None else default_block)
        raise ValueError("unexpected " + method)
    return rpc


def _refresh(native=NATIVE, current=0.02, block=None, gas_exc=None):
    inputs = collect_gas_inputs(make_rpc(block=block, gas_exc=gas_exc))
    return compute_refresh(inputs, native_price_usd=native, current_estimate=current)


def make_pool_meta(tmp_path, gas=0.02):
    meta = {
        "active_liquidity_notional_usd": 1000000.0,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "current_tick": -198144, "dec0": 18, "dec1": 6, "fee": 100,
        "fee_apr_pct": 5.0, "fee_pips": 100, "gas_usd_estimate": gas,
        "input_price_usd": 0.000001, "liquidity": 10748670127530107182,
        "liquidity_raw": 10748670127530107182, "max_impact_bps": 50,
        "protocol": "v3", "range_pct": 20.0, "sigma_daily": 0.05,
        "sqrt_price_x96": 3948718555786119890026495,
        "tick_data": [{"tick_lower": -198184, "tick_upper": -198184,
                       "liquidity_net": 26674215273706257}],
        "tick_spacing": 1, "token0_decimals": 18, "token1_decimals": 6,
        "tvl_usd": 2000000.0,
    }
    p = tmp_path / "pool_meta.json"
    p.write_text(json.dumps(meta, indent=1) + "\n")
    return p, meta


def test_normal_path_in_range():
    r = _refresh()
    assert r["verdict"] == "REFRESHED"
    assert isinstance(r["new_gas_usd"], Decimal)
    assert Decimal("0.46") <= r["new_gas_usd"] <= Decimal("0.47")


def test_gas_price_exception_unavailable_no_write(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    inputs = collect_gas_inputs(make_rpc(gas_exc=ConnectionError("boom")))
    assert inputs["gas_price_wei"] is None
    assert any("eth_gasPrice" in e for e in inputs["errors"])
    r = compute_refresh(inputs, native_price_usd=NATIVE, current_estimate=0.02)
    assert r["verdict"] == "UNAVAILABLE" and r["new_gas_usd"] is None
    assert apply_to_pool_meta(p, r)["written"] is False
    assert p.read_bytes() == orig


def test_empty_block_observed_none_not_zero():
    block = {"number": BLOCK_NUM, "transactions": []}
    inputs = collect_gas_inputs(make_rpc(block=block))
    obs = inputs["observed"]
    assert obs["n"] == 0
    assert obs["median_gas_used"] is None
    assert obs["median_gas_price_wei"] is None
    assert obs["p90_gas_used"] is None
    r = compute_refresh(inputs, native_price_usd=NATIVE, current_estimate=0.02)
    assert r["new_gas_usd"] is not None and r["new_gas_usd"] > 0


def test_native_price_none_unavailable(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    r = _refresh(native=None)
    assert r["verdict"] == "UNAVAILABLE" and r["new_gas_usd"] is None
    assert apply_to_pool_meta(p, r)["written"] is False
    assert p.read_bytes() == orig


def test_native_price_zero_unavailable(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    r = _refresh(native=0)
    assert r["verdict"] == "UNAVAILABLE" and r["new_gas_usd"] is None
    assert apply_to_pool_meta(p, r)["written"] is False
    assert p.read_bytes() == orig


def test_native_price_negative_unavailable(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    r = _refresh(native="-5")
    assert r["verdict"] == "UNAVAILABLE" and r["new_gas_usd"] is None
    assert apply_to_pool_meta(p, r)["written"] is False
    assert p.read_bytes() == orig


def test_sanity_understated_reproduces_real():
    assert _refresh(current=0.02)["sanity"]["verdict"] == "UNDERSTATED"


def test_atomic_write_preserves_22_keys(tmp_path):
    p, orig = make_pool_meta(tmp_path)
    apply_to_pool_meta(p, _refresh(), backup=False)
    new = json.loads(p.read_text())
    for k in orig:
        assert k in new
        assert (new[k] != orig[k]) if k == "gas_usd_estimate" else (new[k] == orig[k])
    assert "gas_provenance" in new and isinstance(new["gas_provenance"], dict)
    assert len(new) == 23


def test_backup_true_creates_bak(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig_text = p.read_text()
    res = apply_to_pool_meta(p, _refresh(), backup=True)
    assert res["written"] is True and res["backup"] is not None
    bak = Path(res["backup"])
    assert bak.name.startswith("pool_meta.json.bak-")
    assert bak.read_text() == orig_text


def test_backup_false_no_bak(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    res = apply_to_pool_meta(p, _refresh(), backup=False)
    assert res["written"] is True and res["backup"] is None
    assert list(tmp_path.glob("pool_meta.json.bak-*")) == []


def test_provenance_six_keys_match_injected():
    prov = _refresh()["provenance"]
    for k in ("gas_price_wei", "native_price_usd", "block_number",
              "receipt_n", "gas_units_total", "computed_at"):
        assert k in prov
    assert prov["gas_price_wei"] == GAS_PRICE_WEI
    assert prov["block_number"] == int(BLOCK_NUM, 16)
    assert prov["receipt_n"] == 8
    assert prov["gas_units_total"] == 800000


def test_idempotent_second_run_same_except_computed_at(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    apply_to_pool_meta(p, _refresh(), backup=False)
    m1 = json.loads(p.read_text())
    apply_to_pool_meta(p, _refresh(), backup=False)
    m2 = json.loads(p.read_text())
    m1["gas_provenance"].pop("computed_at", None)
    m2["gas_provenance"].pop("computed_at", None)
    assert m1 == m2


def test_main_without_apply_file_unchanged(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    mtime = p.stat().st_mtime
    rc = main(["--pool-meta", str(p), "--native-price-usd", NATIVE], rpc_fn=make_rpc())
    assert rc == 0
    assert p.read_bytes() == orig
    assert p.stat().st_mtime == mtime


def test_main_dry_run_returns_zero_no_write(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    orig = p.read_bytes()
    rc = main(["--pool-meta", str(p), "--native-price-usd", NATIVE, "--dry-run"],
              rpc_fn=make_rpc())
    assert rc == 0
    assert p.read_bytes() == orig


def test_written_gas_usd_estimate_precision(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    apply_to_pool_meta(p, _refresh(), backup=False)
    val = json.loads(p.read_text())["gas_usd_estimate"]
    assert isinstance(val, float)
    assert abs(val - float(EXPECTED)) < 1e-6


def test_collect_gas_inputs_normal_shape():
    inputs = collect_gas_inputs(make_rpc())
    assert set(inputs) == {"gas_price_wei", "block_number", "observed", "errors"}
    assert inputs["gas_price_wei"] == GAS_PRICE_WEI
    assert inputs["block_number"] == int(BLOCK_NUM, 16)
    assert inputs["errors"] == []
    assert inputs["observed"]["n"] == 8


def test_new_gas_usd_is_decimal():
    assert isinstance(_refresh()["new_gas_usd"], Decimal)


def test_apply_refreshed_writes(tmp_path):
    p, _ = make_pool_meta(tmp_path)
    res = apply_to_pool_meta(p, _refresh(), backup=False)
    assert res["written"] is True and res["gas_usd_estimate"] > 0
