import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from scripts.lp_rh_reference_freshness_v1_readonly import (
    MAX_REST_AGE_SECS,
    build_attestation,
    main,
    parse_generated_at,
    resolve_freshness,
)

NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
ENDPOINT = "https://api.robinhood.com/rhj/prices"
CHAIN_ID = "robinhood-1"


def _resolve(oracle, rest, **kw):
    return resolve_freshness(oracle_updated_at=oracle, api_generated_at=rest,
                             now=NOW, **kw)


def test_oracle_fresh_onchain():
    r = _resolve(oracle=NOW - timedelta(seconds=10), rest=None)
    assert r["source"] == "ONCHAIN_ORACLE"
    assert r["verdict"] == "FRESH"
    assert r["single_source_risk"] is False


def test_rest_fresh_single_source_risk():
    r = _resolve(oracle=None, rest=NOW - timedelta(seconds=20))
    assert r["source"] == "REST_GENERATED_AT"
    assert r["verdict"] == "FRESH"
    assert r["single_source_risk"] is True


def test_both_none_unavailable():
    r = _resolve(oracle=None, rest=None)
    assert r["verdict"] != "FRESH"
    assert r["verdict"] == "UNAVAILABLE"
    assert r["source"] == "NONE"


def test_rest_over_age_stale():
    r = _resolve(oracle=None, rest=NOW - timedelta(seconds=120))
    assert r["verdict"] != "FRESH"
    assert r["verdict"] == "STALE"
    assert r["source"] == "REST_GENERATED_AT"


def test_rest_unparseable_unavailable():
    r = _resolve(oracle=None, rest="garbage-not-a-timestamp")
    assert r["verdict"] != "FRESH"
    assert r["verdict"] == "UNAVAILABLE"
    assert r["source"] == "NONE"


def test_rest_future_60s_unavailable():
    r = _resolve(oracle=None, rest=NOW + timedelta(seconds=60))
    assert r["verdict"] == "UNAVAILABLE"
    assert "FUTURE_TIMESTAMP" in r["reasons"]


def test_rest_future_2s_still_fresh():
    r = _resolve(oracle=None, rest=NOW + timedelta(seconds=2))
    assert r["verdict"] == "FRESH"


def test_parse_nanosecond_preserves_subsecond():
    d = parse_generated_at("2026-09-09T12:00:00.123456789Z")
    assert d is not None
    assert d.microsecond == 123456
    assert d.tzinfo is not None


def test_parse_none_empty_garbage():
    assert parse_generated_at(None) is None
    assert parse_generated_at("") is None
    assert parse_generated_at("abc") is None


def test_rest_age_exactly_max_fresh():
    r = _resolve(oracle=None, rest=NOW - timedelta(seconds=MAX_REST_AGE_SECS))
    assert r["verdict"] == "FRESH"
    assert r["source"] == "REST_GENERATED_AT"


def test_rest_age_one_over_max_stale():
    r = _resolve(oracle=None,
                 rest=NOW - timedelta(seconds=MAX_REST_AGE_SECS + 1))
    assert r["verdict"] == "STALE"


def test_oracle_stale_rest_fresh_source_consistent():
    r = _resolve(oracle=NOW - timedelta(seconds=100),
                 rest=NOW - timedelta(seconds=20))
    assert r["source"] == "REST_GENERATED_AT"
    assert r["verdict"] == "FRESH"
    assert r["single_source_risk"] is True


def test_attestation_rest_single_source_risk_true():
    r = _resolve(oracle=None, rest=NOW - timedelta(seconds=20))
    a = build_attestation(r, now=NOW, chain_id=CHAIN_ID, endpoint=ENDPOINT)
    assert a["single_source_risk"] is True


def test_attestation_onchain_single_source_risk_false():
    r = _resolve(oracle=NOW - timedelta(seconds=10), rest=None)
    a = build_attestation(r, now=NOW, chain_id=CHAIN_ID, endpoint=ENDPOINT)
    assert a["single_source_risk"] is False


def test_attestation_fail_closed_on_loss_always_true():
    rest_r = _resolve(oracle=None, rest=NOW - timedelta(seconds=20))
    onchain_r = _resolve(oracle=NOW - timedelta(seconds=10), rest=None)
    a_rest = build_attestation(rest_r, now=NOW, chain_id=CHAIN_ID,
                               endpoint=ENDPOINT)
    a_onchain = build_attestation(onchain_r, now=NOW, chain_id=CHAIN_ID,
                                  endpoint=ENDPOINT)
    assert a_rest["fail_closed_on_loss"] is True
    assert a_onchain["fail_closed_on_loss"] is True


def test_attestation_authorized_by():
    r = _resolve(oracle=None, rest=NOW - timedelta(seconds=20))
    a = build_attestation(r, now=NOW, chain_id=CHAIN_ID, endpoint=ENDPOINT)
    assert a["authorized_by"] == "user-decision-20260909"


def test_main_no_out_writes_no_file_returns_zero():
    payload = {
        "resolution": _resolve(oracle=None, rest=NOW - timedelta(seconds=20)),
        "now": NOW.isoformat(),
        "chain_id": CHAIN_ID,
        "endpoint": ENDPOINT,
    }
    with tempfile.TemporaryDirectory() as tmp:
        res_path = os.path.join(tmp, "resolution.json")
        with open(res_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        rc = main(["--resolution-json", res_path])
        assert rc == 0
        assert os.listdir(tmp) == ["resolution.json"]
