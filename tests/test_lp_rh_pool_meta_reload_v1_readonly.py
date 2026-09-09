"""Tests for the per-episode pool-meta reload in the RH Shadow daemon (RH-03f).

The daemon used to read pool_meta once at startup, so a refreshed
gas_usd_estimate never took effect in a long-running daemon.  Now the
pool-meta is re-read at the start of every episode, with last-known-good
fallback on read/parse failure.  Driven with tmp_path JSON files and a fake
episode loop; no network, no wallet, no broadcast, nothing under reports/.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
import threading
from decimal import Decimal

import pytest

from scripts.lp_rh_shadow_daemon_v1_readonly import (
    PoolMetaProvider, load_pool_meta, open_shadow_store,
    pool_meta_hash_of, run_daemon,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store

POOL = "0xpool"
T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T00:00:11Z"


def _write_meta(path, gas):
    meta = {"gas_usd_estimate": gas, "protocol": "v3",
            "attestation_status": "ATTESTED_SAME_BLOCK"}
    path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _base_cfg(live_db):
    return {"live_db": live_db, "pool": POOL, "samples": 20,
            "position_usd": Decimal("1000"), "capital_usd": Decimal("10000"),
            "horizon_hours": 8760, "target_mode": "SHADOW_SCENARIO",
            "pool_meta": None, "pool_meta_hash": "sentinel"}


def _two_round_driver():
    """now_fn/sleep_fn/stop making run_daemon run two episodes and one sleep."""
    calls = {"n": 0}

    def now_fn():
        calls["n"] += 1
        return T0 if calls["n"] <= 3 else T1

    stop = threading.Event()

    def sleep_fn(secs):
        stop.set()

    return now_fn, sleep_fn, stop


def test_load_pool_meta_returns_dict_and_hash(tmp_path):
    p = tmp_path / "meta.json"
    text = json.dumps({"gas_usd_estimate": 0.4})
    p.write_text(text, encoding="utf-8")
    meta, h = load_pool_meta(str(p))
    assert meta == {"gas_usd_estimate": 0.4}
    assert h == pool_meta_hash_of(text)


def test_load_pool_meta_raises_on_bad_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pool_meta(str(tmp_path / "nope.json"))
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_pool_meta(str(p))


def test_second_episode_reads_new_gas(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    m1, _ = provider.load()
    _write_meta(p, 0.4)
    m2, _ = provider.load()
    assert m1["gas_usd_estimate"] == 0.2
    assert m2["gas_usd_estimate"] == 0.4


def test_changed_file_changes_hash(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    _, h1 = provider.load()
    _write_meta(p, 0.4)
    _, h2 = provider.load()
    assert h1 != h2


def test_unchanged_file_same_hash(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    _, h1 = provider.load()
    _, h2 = provider.load()
    assert h1 == h2


def test_deleted_file_falls_back_and_records_error(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    _, h1 = provider.load()
    p.unlink()
    m2, h2 = provider.load()
    assert m2["gas_usd_estimate"] == 0.2
    assert h2 == h1
    assert provider.reload_errors


def test_invalid_json_falls_back_and_records_error(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    _, h1 = provider.load()
    p.write_text("{broken", encoding="utf-8")
    m2, h2 = provider.load()
    assert m2["gas_usd_estimate"] == 0.2
    assert h2 == h1
    assert provider.reload_errors


def test_failure_never_yields_empty_dict(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.4005)
    provider = PoolMetaProvider(str(p))
    provider.load()
    p.unlink()
    m2, _ = provider.load()
    assert m2 is not None and m2 != {}
    assert m2["gas_usd_estimate"] == 0.4005
    assert m2["gas_usd_estimate"] is not None
    assert m2["gas_usd_estimate"] != 0


def test_recoverable_after_consecutive_failures(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    provider.load()
    p.unlink()
    provider.load()
    provider.load()
    assert len(provider.reload_errors) == 2
    _write_meta(p, 0.5)
    m3, _ = provider.load()
    assert m3["gas_usd_estimate"] == 0.5


def test_episode_uses_start_value_even_if_file_changes_mid_episode(tmp_path):
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    meta, h = provider.load()
    _write_meta(p, 0.9)
    step_hashes = [h for _ in range(3)]
    assert len(set(step_hashes)) == 1
    assert meta["gas_usd_estimate"] == 0.2


def test_run_daemon_uses_provider_hash(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live); live.commit()
    shadow = open_shadow_store(":memory:")
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    expected = pool_meta_hash_of(p.read_text(encoding="utf-8"))
    provider = PoolMetaProvider(str(p))
    now_fn, sleep_fn, stop = _two_round_driver()
    rc = run_daemon(_base_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                    period_secs=10, now_fn=now_fn, sleep_fn=sleep_fn,
                    stop_event=stop, pool_meta_provider=provider)
    assert rc == 0
    hashes = [r[0] for r in shadow.execute(
        "select pool_meta_hash from rh_shadow_episodes")]
    assert hashes and all(h == expected for h in hashes)


def test_main_first_load_failure_propagates(tmp_path, monkeypatch):
    import scripts.lp_rh_shadow_daemon_v1_readonly as mod
    live = open_store(tmp_path / "live.db"); migrate(live); live.commit()
    monkeypatch.setattr(mod, "LIVE_DB", str(tmp_path / "live.db"))
    with pytest.raises(FileNotFoundError):
        mod.main(["--once", "--db", str(tmp_path / "s.db"), "--pool", POOL,
                  "--pool-meta-json", str(tmp_path / "missing.json"),
                  "--position-usd", "1000", "--capital-usd", "10000",
                  "--horizon-hours", "8760"])


def _run_two_episodes(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live); live.commit()
    shadow = open_shadow_store(":memory:")
    p = tmp_path / "meta.json"
    _write_meta(p, 0.2)
    provider = PoolMetaProvider(str(p))
    now_fn, sleep_fn, stop = _two_round_driver()
    rc = run_daemon(_base_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                    period_secs=10, now_fn=now_fn, sleep_fn=sleep_fn,
                    stop_event=stop, pool_meta_provider=provider)
    assert rc == 0
    return shadow


def test_regression_pool_field_unaffected(tmp_path):
    shadow = _run_two_episodes(tmp_path)
    pools = [r[0] for r in shadow.execute("select pool from rh_shadow_episodes")]
    assert pools and all(p == POOL for p in pools)


def test_regression_position_usd_unaffected(tmp_path):
    shadow = _run_two_episodes(tmp_path)
    pos = [r[0] for r in shadow.execute(
        "select position_usd from rh_shadow_episodes")]
    assert pos and all(p == "1000" for p in pos)


def test_regression_capital_usd_unaffected(tmp_path):
    shadow = _run_two_episodes(tmp_path)
    cap = [r[0] for r in shadow.execute(
        "select capital_usd from rh_shadow_episodes")]
    assert cap and all(c == "10000" for c in cap)
