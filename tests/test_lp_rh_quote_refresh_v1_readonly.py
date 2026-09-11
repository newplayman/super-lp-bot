"""Tests for lp_rh_quote_refresh_v1.

All tests are offline (mock fetch_fn / tmp_path JSON).
Validates fail-close behavior, depeg calculation, atomic writes, and zero silent fallbacks.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_quote_refresh_v1 import (  # noqa: E402
    COINGECKO_URL,
    apply_to_pool_meta,
    build_quote_refresh,
    main,
)


def _make_pool_meta(tmp_path, *, with_quote: bool = True) -> Path:
    meta = {
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "current_tick": -198144,
        "token0": "0x0bd7d308f8e1639fab988df18a8011f41eacad73",
        "token1": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
        "fee_apr_pct": 27.34,
    }
    if with_quote:
        meta["quote_usd_per_token1"] = {
            "value": "1.0",
            "source": "coingecko:global-dollar/usd (simple/price, free tier, no key)",
            "observed_at": "2026-09-10T01:50:10Z",
            "ttl_secs": 86400,
            "note": "old quote",
        }
    p = tmp_path / "pool_meta.json"
    p.write_text(json.dumps(meta, indent=2))
    return p


def test_1_normal_response_status_ok_and_fields():
    payload = {"global-dollar": {"usd": 1.0001}}
    now_fixed = datetime(2026, 9, 11, 13, 0, 0, tzinfo=timezone.utc)
    res = build_quote_refresh(payload, now=now_fixed)

    assert res["status"] == "OK"
    quote = res["quote"]
    assert quote is not None
    assert quote["value"] == "1.0001"
    assert quote["observed_at"] == "2026-09-11T13:00:00Z"
    assert quote["ttl_secs"] == 86400
    assert quote["source"] == "coingecko:global-dollar/usd (simple/price, free tier, no key)"
    assert quote["raw_fragment"] == {"global-dollar": {"usd": 1.0001}}
    assert "USDG = Global Dollar" in quote["note"]
    assert "0.0100%" in quote["note"]
    assert quote["depeg_pct"] == "0.0100"


def test_2_real_depeg_0_97_written_not_rejected():
    payload = {"global-dollar": {"usd": 0.97}}
    res = build_quote_refresh(payload)

    assert res["status"] == "OK"
    quote = res["quote"]
    assert quote is not None
    assert quote["value"] == "0.97"
    assert pytest.approx(float(quote["depeg_pct"]), rel=1e-3) == -3.0
    assert quote["depeg_pct"] == "-3.00"
    assert "-3.0000%" in quote["note"]


def test_3_request_failure_and_non_json_unavailable_no_write(tmp_path):
    p = _make_pool_meta(tmp_path)
    orig_bytes = p.read_bytes()
    orig_mtime = p.stat().st_mtime_ns

    # Case 3a: Non-JSON string
    r_bad_json = build_quote_refresh("not a json {abc")
    assert r_bad_json["status"].startswith("UNAVAILABLE:")
    assert r_bad_json["quote"] is None
    apply_res = apply_to_pool_meta(p, r_bad_json)
    assert apply_res["written"] is False
    assert p.read_bytes() == orig_bytes
    assert p.stat().st_mtime_ns == orig_mtime

    # Case 3b: Request exception via CLI
    def _failing_fetch():
        raise ConnectionError("Simulated network outage")

    rc = main(["--pool-meta", str(p), "--apply"], fetch_fn=_failing_fetch)
    assert rc == 1
    assert p.read_bytes() == orig_bytes
    assert p.stat().st_mtime_ns == orig_mtime


def test_4_missing_target_field_unavailable_no_write(tmp_path):
    p = _make_pool_meta(tmp_path)
    orig_bytes = p.read_bytes()

    for bad_payload in [
        {},
        {"wrong-coin": {"usd": 1.0}},
        {"global-dollar": {}},
        {"global-dollar": {"eur": 0.95}},
        {"global-dollar": None},
    ]:
        res = build_quote_refresh(bad_payload)
        assert res["status"].startswith("UNAVAILABLE:")
        assert res["quote"] is None
        assert apply_to_pool_meta(p, res)["written"] is False
        assert p.read_bytes() == orig_bytes


def test_5_zero_negative_non_numeric_unavailable_no_write(tmp_path):
    p = _make_pool_meta(tmp_path)
    orig_bytes = p.read_bytes()

    for bad_val in [0, 0.0, -1.0, -0.0001, "NaN", "invalid", None]:
        res = build_quote_refresh({"global-dollar": {"usd": bad_val}})
        assert res["status"].startswith("UNAVAILABLE:")
        assert res["quote"] is None
        assert apply_to_pool_meta(p, res)["written"] is False
        assert p.read_bytes() == orig_bytes


def test_6_absurd_value_50_unavailable_no_write(tmp_path):
    p = _make_pool_meta(tmp_path)
    orig_bytes = p.read_bytes()

    for absurd_val in [50.0, 0.05, 10.0, 0.1, 999.0]:
        res = build_quote_refresh({"global-dollar": {"usd": absurd_val}})
        assert res["status"].startswith("UNAVAILABLE:absurd_value")
        assert res["quote"] is None
        assert apply_to_pool_meta(p, res)["written"] is False
        assert p.read_bytes() == orig_bytes


def test_7_no_silent_fallback_to_one_on_failure(tmp_path):
    p = _make_pool_meta(tmp_path, with_quote=False)
    orig_bytes = p.read_bytes()
    orig_dict = json.loads(p.read_text())
    assert "quote_usd_per_token1" not in orig_dict

    failures = [
        {"global-dollar": {"usd": 50.0}},
        {"global-dollar": {"usd": -1.0}},
        {"wrong-key": 1.0},
        None,
        "invalid json",
    ]
    for bad in failures:
        res = build_quote_refresh(bad)
        assert res["status"].startswith("UNAVAILABLE:")
        applied = apply_to_pool_meta(p, res)
        assert applied["written"] is False

    content = p.read_text()
    assert "quote_usd_per_token1" not in content
    assert '"value": "1.0"' not in content
    assert p.read_bytes() == orig_bytes


def test_8_apply_success_creates_backup_and_preserves_other_fields(tmp_path):
    prod_meta_path = REPO_ROOT / "reports/lp_rh/pool_meta.json"
    p = tmp_path / "pool_meta.json"
    p.write_bytes(prod_meta_path.read_bytes())

    orig_bytes = p.read_bytes()
    orig_meta = json.loads(orig_bytes)

    fresh_payload = {"global-dollar": {"usd": 1.0001}}
    refresh = build_quote_refresh(fresh_payload)
    assert refresh["status"] == "OK"

    res = apply_to_pool_meta(p, refresh, backup=True)
    assert res["written"] is True
    assert res["backup"] is not None

    bak_path = Path(res["backup"])
    assert bak_path.exists()
    assert bak_path.name.startswith("pool_meta.json.bak-")
    assert bak_path.read_bytes() == orig_bytes

    updated_meta = json.loads(p.read_text())
    assert updated_meta["quote_usd_per_token1"]["value"] == "1.0001"

    assert set(updated_meta.keys()) == set(orig_meta.keys())
    for k, v in orig_meta.items():
        if k != "quote_usd_per_token1":
            assert updated_meta[k] == v

    orig_lines = orig_bytes.decode().splitlines()
    new_lines = p.read_text().splitlines()
    idx_orig_quote = orig_lines.index('  "quote_usd_per_token1": {')
    idx_orig_token0 = orig_lines.index('  "token0": "0x0bd7d308f8e1639fab988df18a8011f41eacad73",')
    idx_new_quote = new_lines.index('  "quote_usd_per_token1": {')
    idx_new_token0 = new_lines.index('  "token0": "0x0bd7d308f8e1639fab988df18a8011f41eacad73",')

    assert orig_lines[:idx_orig_quote] == new_lines[:idx_new_quote]
    assert orig_lines[idx_orig_token0:] == new_lines[idx_new_token0:]


def test_9_dry_run_default_no_write(tmp_path):
    prod_meta_path = REPO_ROOT / "reports/lp_rh/pool_meta.json"
    p = tmp_path / "pool_meta.json"
    p.write_bytes(prod_meta_path.read_bytes())

    orig_bytes = p.read_bytes()
    orig_mtime = p.stat().st_mtime_ns

    mock_fetch = lambda: {"global-dollar": {"usd": 0.999994}}

    rc1 = main(["--pool-meta", str(p)], fetch_fn=mock_fetch)
    assert rc1 == 0
    assert p.read_bytes() == orig_bytes
    assert p.stat().st_mtime_ns == orig_mtime
    assert list(tmp_path.glob("pool_meta.json.bak-*")) == []

    rc2 = main(["--pool-meta", str(p), "--dry-run"], fetch_fn=mock_fetch)
    assert rc2 == 0
    assert p.read_bytes() == orig_bytes
    assert p.stat().st_mtime_ns == orig_mtime
    assert list(tmp_path.glob("pool_meta.json.bak-*")) == []

