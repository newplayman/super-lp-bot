from __future__ import annotations

import http.client
import json
import os
import socket
import sqlite3
import threading
from pathlib import Path

import pytest

from scripts import lp_panel_server_v1_readonly as panel


TOKEN = "p" * 40
BOT_TOKEN_SHAPE = "1234567890:" + "A" * 35
RPC_PATH_KEY = "K" * 40


def make_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE pool_snapshots(as_of TEXT,pool TEXT);
        CREATE TABLE opportunity_scores(
          as_of TEXT,pool TEXT,accepted INTEGER,rejection_reason TEXT,score_json TEXT,
          netcover_ratio REAL
        );
        CREATE TABLE market_sessions(
          as_of TEXT,instrument_id TEXT,market_session TEXT,source_timestamp TEXT,
          reference_price REAL,basis_bps REAL,redemption_status TEXT,source TEXT
        );
        CREATE TABLE shadow_gate_observations(
          as_of TEXT,source_run TEXT,tick INTEGER,predicted_fee_usd REAL,
          actual_fee_usd REAL,fee_prediction_status TEXT,shadow_net_pnl_usd REAL,
          simulated_drawdown_pct REAL,rpc_health TEXT
        );
        CREATE TABLE shadow_positions(
          source_run TEXT,position_identity TEXT,first_seen_as_of TEXT,last_seen_as_of TEXT
        );
        CREATE TABLE rpc_severe_incidents(resolved_at TEXT);
        """
    )
    connection.executemany(
        "INSERT INTO pool_snapshots VALUES(?,?)",
        [("2026-08-09T00:00:00+00:00", "pool-a"), ("2026-08-09T00:00:00+00:00", "pool-b")],
    )
    connection.executemany(
        "INSERT INTO opportunity_scores VALUES(?,?,?,?,?,?)",
        [
            ("2026-08-09T00:00:00+00:00", "pool-a", 0, "NETCOVER", json.dumps({"resolve_status": "OK", "netcover_gate_status": "FAIL", "gates": {"quality": True, "netcover_shadow": False}}), 0.8),
            ("2026-08-09T00:00:00+00:00", "pool-b", 1, None, json.dumps({"resolve_status": "OK", "netcover_gate_status": "PASS", "gates": {"quality": True, "netcover_shadow": True}}), 1.7),
        ],
    )
    connection.executemany(
        "INSERT INTO market_sessions VALUES(?,?,?,?,?,?,?,?)",
        [
            ("2026-08-09T00:00:00+00:00", "backed:SPYx", "PRIMARY_CLOSED", None, 100.0, 2.0, "OPEN", "xstocks_official"),
            ("2026-08-09T00:00:00+00:00", "robinhood:SPY", "PRIMARY_CLOSED", None, 101.0, None, "OPEN", "robinhood_stock_token"),
        ],
    )
    connection.execute(
        "INSERT INTO shadow_gate_observations VALUES(?,?,?,?,?,?,?,?,?)",
        ("2026-08-09T00:00:00+00:00", "run", 0, 10.0, 9.0, "COMPLETE", 1.0, 2.0, "NORMAL"),
    )
    connection.executemany(
        "INSERT INTO shadow_positions VALUES(?,?,?,?)",
        [
            ("run", "pool-a", "2026-08-09T00:00:00+00:00", "2026-08-09T00:00:00+00:00"),
            ("run", "pool-a:reentry:1", "2026-08-09T00:00:00+00:00", "2026-08-09T00:00:00+00:00"),
        ],
    )
    connection.commit()
    connection.close()


def make_files(root: Path) -> tuple[Path, Path, Path, Path]:
    heartbeat = root / "heartbeat.jsonl"
    heartbeat.write_text(
        json.dumps(
            {
                "ts_utc": "2026-08-09T00:00:01+00:00",
                "portfolio_nav_usd": 51.0,
                "portfolio_net_usd": 1.0,
                "by_pool": [{"pool": "pool-a", "symbol": "A-B", "pnl_vs_usdc": 1.0, "api_key": "do-not-emit"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    portfolio = root / "portfolio.csv"
    portfolio.write_text("ts_utc,tick,portfolio_net_usd\n2026-08-09T00:00:01+00:00,0,1\n", encoding="utf-8")
    rwa = root / "rwa"
    rwa.mkdir()
    (rwa / "SPYx.jsonl").write_text(
        json.dumps(
            {
                "as_of": "2026-08-09T00:00:02+00:00",
                "instrument_id": "robinhood:SPY",
                "shadow_only": True,
                "basis_bps": 3,
                "bot_token": BOT_TOKEN_SHAPE,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    probe = root / "probe"
    probe.mkdir()
    (probe / "probe_solana.txt").write_text(
        f"UP slot=1 https://user:pass@rpc.example.test:8545/v2/{RPC_PATH_KEY}"
        "?api-key=must-not-leak\n429\n",
        encoding="utf-8",
    )
    return heartbeat, portfolio, rwa, probe


def make_builder(tmp_path: Path, *, missing: bool = False) -> panel.StateBuilder:
    db = tmp_path / "scanner.db"
    if not missing:
        make_db(db)
        heartbeat, portfolio, rwa, probe = make_files(tmp_path)
    else:
        heartbeat = tmp_path / "missing-heartbeat"
        portfolio = tmp_path / "missing-csv"
        rwa = tmp_path / "missing-rwa"
        probe = tmp_path / "missing-probe"
    return panel.StateBuilder(db=db, heartbeat=heartbeat, portfolio_csv=portfolio, rwa_dir=rwa, probe_dir=probe)


def make_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, auth: bool = True, limit: int = 60, missing: bool = False):
    if auth:
        monkeypatch.setenv(panel.TOKEN_ENV, TOKEN)
    args = panel.parser().parse_args(
        [
            "--host", "127.0.0.1", "--port", "0", "--db", str(tmp_path / "scanner.db"),
            "--heartbeat", str(tmp_path / "heartbeat.jsonl"), "--portfolio-csv", str(tmp_path / "portfolio.csv"),
            "--rwa-jsonl-dir", str(tmp_path / "rwa"), "--probe-dir", str(tmp_path / "probe"),
            "--access-log", str(tmp_path / "access.log"), "--rate-limit", str(limit),
        ]
        + ([] if auth else ["--no-auth"])
    )
    if not missing:
        make_db(tmp_path / "scanner.db")
        make_files(tmp_path)
    server = panel.build_server(args)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def request(server, method="GET", path="/api/state.json", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), body


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_default_bind_port_and_inline_frontend_have_complete_sections():
    args = panel.parser().parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 8899
    assert "https://" not in panel.PANEL_HTML
    assert "Gate 六项" in panel.PANEL_HTML
    for text in ("净值与回撤", "23 字段归因", "漏斗健康", "RWA 三锚", "RPC 健康", "PAPER / READ-ONLY"):
        assert text in panel.PANEL_HTML
    assert "/api/state.json" in panel.PANEL_HTML


def test_token_is_required_at_startup_and_minimum_32_chars(tmp_path, monkeypatch):
    monkeypatch.delenv(panel.TOKEN_ENV, raising=False)
    args = panel.parser().parse_args(["--host", "127.0.0.1", "--port", "0", "--access-log", str(tmp_path / "a.log")])
    with pytest.raises(SystemExit, match="at least 32"):
        panel.build_server(args)
    monkeypatch.setenv(panel.TOKEN_ENV, "x" * 31)
    with pytest.raises(SystemExit, match="at least 32"):
        panel.build_server(args)


def test_authentication_missing_wrong_query_and_header(tmp_path, monkeypatch):
    server, thread = make_server(tmp_path, monkeypatch)
    try:
        assert request(server)[0] == 401
        assert request(server, path="/api/state.json?token=wrong")[0] == 401
        status, _, body = request(server, path=f"/api/state.json?token={TOKEN}")
        assert status == 200
        assert json.loads(body)["mode"].startswith("PAPER / READ-ONLY")
        assert request(server, headers={"X-Panel-Token": TOKEN})[0] == 200
    finally:
        stop(server, thread)


def test_unauthorized_response_and_access_log_never_expose_token(tmp_path, monkeypatch):
    server, thread = make_server(tmp_path, monkeypatch)
    try:
        _, _, body = request(server, path=f"/api/state.json?token={TOKEN}wrong")
        assert b"pool-a" not in body
        assert TOKEN.encode() not in body
    finally:
        stop(server, thread)
    log = (tmp_path / "access.log").read_text()
    assert TOKEN not in log
    assert "?token=" not in log


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_non_get_methods_are_405(tmp_path, monkeypatch, method):
    server, thread = make_server(tmp_path, monkeypatch)
    try:
        status, headers, _ = request(server, method=method, headers={"Content-Length": "0"})
        assert status == 405
        assert headers["Allow"] == "GET"
    finally:
        stop(server, thread)


def test_only_whitelisted_paths_and_request_body_limit(tmp_path, monkeypatch):
    server, thread = make_server(tmp_path, monkeypatch)
    try:
        assert request(server, path=f"/../../etc/passwd?token={TOKEN}")[0] == 404
        assert request(server, path=f"/api/state.json?file=/etc/passwd&token={TOKEN}")[0] == 200
        assert request(
            server, path=f"/api/state.json?token={TOKEN}", headers={"Content-Length": str(panel.MAX_REQUEST_BODY_BYTES + 1)}
        )[0] == 413
        too_many = "&".join(f"p{i}=x" for i in range(9))
        assert request(server, path=f"/api/state.json?{too_many}")[0] == 400
    finally:
        stop(server, thread)


def test_payload_exposes_only_probe_origin_and_scrubs_generic_path_key(tmp_path):
    builder = make_builder(tmp_path)
    state = builder.build()
    encoded = json.dumps(state)
    assert "do-not-emit" not in encoded
    assert BOT_TOKEN_SHAPE not in encoded
    assert "must-not-leak" not in encoded
    assert RPC_PATH_KEY not in encoded
    assert "user:pass" not in encoded
    assert "/v2/" not in encoded
    assert "api_key" not in encoded
    assert "private_key" not in encoded
    assert state["rpc"]["chains"][0]["endpoints"][0]["endpoint"] == "https://rpc.example.test:8545"


def test_http_response_has_no_secret_shapes(tmp_path, monkeypatch):
    server, thread = make_server(tmp_path, monkeypatch)
    try:
        status, _, body = request(server, path=f"/api/state.json?token={TOKEN}")
        assert status == 200
        text = body.decode()
        assert TOKEN not in text
        assert BOT_TOKEN_SHAPE not in text
        assert not panel._SENSITIVE_VALUE.search(text)
    finally:
        stop(server, thread)


def test_rate_limit_is_per_ip_and_enforced_over_http(tmp_path, monkeypatch):
    server, thread = make_server(tmp_path, monkeypatch, auth=False, limit=2)
    try:
        assert request(server)[0] == 200
        assert request(server)[0] == 200
        assert request(server)[0] == 429
    finally:
        stop(server, thread)


def test_no_auth_prints_warning_and_records_it(tmp_path, monkeypatch, capsys):
    server, thread = make_server(tmp_path, monkeypatch, auth=False)
    try:
        assert "authentication DISABLED" in capsys.readouterr().err
    finally:
        stop(server, thread)
    assert "NO_AUTH_ENABLED" in (tmp_path / "access.log").read_text()


def test_missing_all_sources_degrades_without_exception(tmp_path):
    state = make_builder(tmp_path, missing=True).build()
    assert state["sources"]["scanner_db"]["status"] == "尚未开始"
    assert state["sources"]["heartbeat"]["status"] == "尚未开始"
    assert state["positions"] == []
    assert state["nav_series"] == []


def test_sqlite_connection_is_read_only_and_does_not_hold_write_lock(tmp_path):
    path = tmp_path / "scanner.db"
    make_db(path)
    readonly = panel.open_sqlite_readonly(path)
    with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
        readonly.execute("INSERT INTO pool_snapshots VALUES('x','y')")
    writer = sqlite3.connect(path, timeout=0.1)
    writer.execute("INSERT INTO pool_snapshots VALUES('2026-08-10','new')")
    writer.commit()
    writer.close()
    readonly.close()


def test_gate_reports_unique_identity_and_unique_root_pool_separately(tmp_path):
    builder = make_builder(tmp_path)
    state = builder.build()
    assert state["gate"]["unique_position_identity"] == 2
    assert state["gate"]["unique_root_pool"] == 1
    assert len(state["gate"]["checks"]) == 6
    positions = state["gate"]["checks"]["simulated_positions"]
    assert positions["unique_position_identities"] == 2
    assert positions["unique_root_pools"] == 1
    assert positions["status"] == "FAIL"


def test_gate_root_suffix_and_near_zero_pnl_match_canonical_semantics(tmp_path):
    builder = make_builder(tmp_path)
    connection = sqlite3.connect(builder.db)
    connection.execute(
        "INSERT INTO shadow_positions VALUES(?,?,?,?)",
        ("run", "pool-a:reentry:1:reentry:2", "2026-08-09T00:00:00+00:00", "2026-08-09T00:00:00+00:00"),
    )
    connection.execute("UPDATE shadow_gate_observations SET shadow_net_pnl_usd=?", (5e-10,))
    connection.commit()
    connection.close()
    state = builder.build()
    assert state["gate"]["unique_root_pool"] == 1
    pnl = state["gate"]["checks"]["shadow_net_pnl_usd"]
    assert pnl["value"] == 0.0
    assert pnl["raw_value"] == 5e-10
    assert pnl["status"] == "FAIL"


def test_gate_non_finite_drawdown_is_unknown(tmp_path):
    builder = make_builder(tmp_path)
    connection = sqlite3.connect(builder.db)
    connection.execute("UPDATE shadow_gate_observations SET simulated_drawdown_pct=?", (float("inf"),))
    connection.commit()
    connection.close()
    drawdown = builder.build()["gate"]["checks"]["simulated_drawdown_pct"]
    assert drawdown["value"] is None
    assert drawdown["status"] == "UNKNOWN"


def test_state_has_separate_nav_and_net_and_full_data_sections(tmp_path):
    state = make_builder(tmp_path).build()
    assert state["nav_series"][-1]["portfolio_nav_usd"] == 51.0
    assert state["nav_series"][-1]["portfolio_net_usd"] == 1.0
    assert state["nav_series"][-1]["portfolio_drawdown_pct"] == 0.0
    assert state["positions"][0]["netcover_ratio"] == 0.8
    assert state["positions"][0]["netcover_gate_status"] == "FAIL"
    assert state["funnel"] == {
        "cycle_as_of": "2026-08-09T00:00:00+00:00",
        "screened": 2,
        "top": 2,
        "resolved": 2,
        "scored": 2,
        "accepted": 1,
        "gate_rejections": {"netcover_shadow": 1},
        "rejection_reasons": {"NETCOVER": 1},
    }
    assert len(state["rwa"]["symbols"]) == 1
    assert len(state["rwa"]["symbols"][0]["anchors"]) == 2
    assert state["rpc"]["chains"]


def test_systemd_unit_is_hardened_and_has_no_embedded_credential():
    unit = (panel.REPO_ROOT / "deploy/systemd/lpbot-panel-shadow.service").read_text()
    for required in (
        "User=lpbot", "NoNewPrivileges=true", "ProtectSystem=strict",
        "ReadWritePaths=/opt/lpbot/lp-bot-v3-origin-check/reports/lp_panel",
        "CapabilityBoundingSet=", "PassEnvironment=LPBOT_PANEL_TOKEN",
        "--host 0.0.0.0", "--port 8899",
    ):
        assert required in unit
    assert "Environment=LPBOT_PANEL_TOKEN=" not in unit
    assert "--no-auth" not in unit


def test_handoff_runner_output_matches_panel_inputs_and_imports_token_environment():
    handoff = (panel.REPO_ROOT / "HANDOFF_M0_READY_CN.md").read_text()
    unit = (panel.REPO_ROOT / "deploy/systemd/lpbot-panel-shadow.service").read_text()
    runner_dir = "reports/lp_portfolio_paper_runner/latest"
    absolute_runner_dir = f"{panel.REPO_ROOT}/{runner_dir}"

    # Both commander-approved long-running runner launch forms (nohup and
    # transient unit) must write where both panel launch forms read.
    assert sum(
        line.strip().startswith(f"--out {runner_dir}")
        for line in handoff.splitlines()
    ) == 2
    assert f"--heartbeat {runner_dir}/heartbeat.jsonl" in handoff
    assert f"--portfolio-csv {runner_dir}/portfolio_state_hourly.csv" in handoff
    assert f"--heartbeat {absolute_runner_dir}/heartbeat.jsonl" in unit
    assert f"--portfolio-csv {absolute_runner_dir}/portfolio_state_hourly.csv" in unit
    assert runner_dir in handoff.split("install -d -m 700", 1)[1].splitlines()[0]

    import_command = (
        "sudo --preserve-env=LPBOT_PANEL_TOKEN systemctl "
        "import-environment LPBOT_PANEL_TOKEN"
    )
    assert import_command in handoff
    assert handoff.index(import_command) < handoff.index(
        "sudo systemctl enable --now lpbot-panel-shadow.service"
    )

    first_unit_install = handoff.index(
        "sudo install -m 0644 deploy/systemd/lpbot-scanner-shadow.service"
    )
    first_enable = handoff.index(
        "sudo systemctl enable --now lpbot-scanner-shadow.service"
    )
    owner_prep_prefix = "sudo install -d -o lpbot -g lpbot -m 0700 "
    for relative_dir in (
        "reports/lp_panel",
        "reports/lp_scanner",
        "reports/lp_scanner/rwa_sessions",
        runner_dir,
    ):
        owner_prep = f"{owner_prep_prefix}{panel.REPO_ROOT}/{relative_dir}"
        assert owner_prep in handoff
        assert handoff.index(owner_prep) < first_unit_install < first_enable

    ownership_commands = {
        line.strip()
        for line in handoff.splitlines()
        if line.strip().startswith("sudo chown -R lpbot:lpbot ")
    }
    expected_ownership_commands = {
        f"sudo chown -R lpbot:lpbot {panel.REPO_ROOT}/reports/lp_scanner",
        f"sudo chown -R lpbot:lpbot {panel.REPO_ROOT}/reports/lp_panel",
        f"sudo chown -R lpbot:lpbot {panel.REPO_ROOT}/{runner_dir}",
    }
    assert ownership_commands == expected_ownership_commands
    assert all(handoff.index(command) < first_unit_install for command in ownership_commands)


def test_source_has_no_execution_or_static_file_server_surface():
    source = Path(panel.__file__).read_text()
    for forbidden in ("import subprocess", "SimpleHTTPRequestHandler", "os.system(", "send_transaction("):
        assert forbidden not in source
    assert panel.ALLOWED_PATHS == {"/", "/api/state.json"}
