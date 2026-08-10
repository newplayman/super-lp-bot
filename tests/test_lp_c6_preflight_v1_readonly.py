from __future__ import annotations

import json
import os
import sqlite3

from scripts.lp_c6_preflight_v1_readonly import (
    check_broadcast_lock,
    check_candidate,
    check_exit_only,
    check_keystore_isolation,
    check_rpc,
    evaluate,
)


def _scanner_db(path, accepted=0, unresolved=0):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE opportunity_scores(as_of TEXT, accepted INTEGER);
        CREATE TABLE rpc_severe_incidents(resolved_at TEXT);
        """
    )
    connection.execute("INSERT INTO opportunity_scores VALUES ('2026-08-10T00:00:00+00:00', ?)", (accepted,))
    for _ in range(unresolved):
        connection.execute("INSERT INTO rpc_severe_incidents VALUES (NULL)")
    connection.commit()
    connection.close()


def test_candidate_requires_at_least_one_latest_accepted(tmp_path):
    db = tmp_path / "scanner.db"
    _scanner_db(db, accepted=0)
    assert not check_candidate(db).passed
    connection = sqlite3.connect(db)
    connection.execute("INSERT INTO opportunity_scores VALUES ('2026-08-10T00:00:00+00:00', 1)")
    connection.commit(); connection.close()
    assert check_candidate(db).passed


def test_broadcast_lock_proves_transport_unreached(tmp_path):
    unit = tmp_path / "executor.service"
    unit.write_text("Environment=LIVE_TRADING=false\n")
    result = check_broadcast_lock({"LIVE_TRADING": "false"}, unit)
    assert result.passed
    assert result.evidence["transport_send_calls"] == 0
    assert not check_broadcast_lock({"LIVE_TRADING": "true"}, unit).passed


def test_keystore_check_stats_but_does_not_read_contents(tmp_path):
    key = tmp_path / "key.json"
    password = tmp_path / "password"
    key.write_text("sentinel-key-content")
    password.write_text("sentinel-password")
    os.chmod(key, 0o600); os.chmod(password, 0o600)
    result = check_keystore_isolation(key, password, os.getuid(), os.getuid() + 1)
    assert result.passed
    assert result.evidence["keystore"]["contents_read"] is False
    os.chmod(password, 0o644)
    assert not check_keystore_isolation(key, password, os.getuid(), os.getuid() + 1).passed


def test_exit_only_blocks_mint_and_allows_revoke_without_network():
    result = check_exit_only()
    assert result.passed
    assert result.evidence == {"mint_blocked": True, "revoke_allowed": True, "network_calls": 0}


def test_rpc_requires_chain_block_and_no_unresolved_incident(tmp_path):
    db = tmp_path / "scanner.db"
    _scanner_db(db, unresolved=0)
    probe = lambda: {"chain_id": 8453, "block_number": 1, "state": "DEGRADED"}
    assert check_rpc(db, probe).passed
    bad = tmp_path / "bad.db"
    _scanner_db(bad, unresolved=1)
    assert not check_rpc(bad, probe).passed


def test_evaluate_fails_closed_on_missing_deployment_evidence(tmp_path):
    db = tmp_path / "scanner.db"
    _scanner_db(db, accepted=0)
    c3 = tmp_path / "c3.json"
    c3.write_text(json.dumps({"verdict": "PASS"}))
    unit = tmp_path / "executor.service"
    unit.write_text("Environment=LIVE_TRADING=false\n")
    report = evaluate(
        scanner_db=db, c3_path=c3, systemd_path=unit,
        environ={"LIVE_TRADING": "false"},
        rpc_probe=lambda: {"chain_id": 8453, "block_number": 1, "state": "NORMAL"},
    )
    assert report["overall"] == "FAIL"
    assert report["safety"]["signed"] is False
    assert report["safety"]["broadcast_count"] == 0
