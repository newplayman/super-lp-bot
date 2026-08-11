from __future__ import annotations

import json
import sqlite3

from scripts.lp_funnel_autopsy_v1_readonly import (
    GATE_ORDER,
    build_report,
    closest_failures,
    decay_table,
    first_failed_gate,
    gate_bits,
    independent_feasibility_cohort,
    render_markdown,
    recomputed_accepted,
)


def _row(name: str, **changes):
    row = {
        "symbol": name,
        "llama_pool_id": name,
        "tier_quality": "A",
        "yield_cover": 2.0,
        "enter_frac": 1.0,
        "entry_eligible": True,
        "netcover": 2.0,
        "netcover_ratio": 2.0,
        "netcover_pass": True,
        "position_cap_usd": 60.0,
        "position_cap_hard_tvl_share_ok": True,
        "position_cap_pass": True,
        "gates": {
            "status_ok": True,
            "quality": True,
            "yield_cover": True,
            "stable": True,
        },
    }
    row.update(changes)
    return row


def test_terminal_acceptance_is_complete_conjunction():
    passing = _row("pass")
    assert recomputed_accepted(passing)
    for gate in GATE_ORDER:
        broken = _row(gate)
        if gate in {"resolution_status", "asset_quality", "yield_cover", "multiwindow_stable"}:
            key = {
                "resolution_status": "status_ok",
                "asset_quality": "quality",
                "yield_cover": "yield_cover",
                "multiwindow_stable": "stable",
            }[gate]
            broken["gates"] = dict(broken["gates"], **{key: False})
        elif gate == "entry_eligible":
            broken["entry_eligible"] = False
        elif gate == "netcover":
            broken["netcover_pass"] = False
        else:
            broken["position_cap_pass"] = False
        assert not recomputed_accepted(broken)
        assert first_failed_gate(broken) == gate


def test_decay_is_sequential_and_closest_only_uses_rows_reaching_gate():
    rows = [
        _row("pass"),
        _row("quality", tier_quality="C", gates={"status_ok": True, "quality": False, "yield_cover": True, "stable": True}),
        _row("yield-near", yield_cover=0.9, gates={"status_ok": True, "quality": True, "yield_cover": False, "stable": True}),
        _row("yield-far", yield_cover=0.2, gates={"status_ok": True, "quality": True, "yield_cover": False, "stable": True}),
        _row("stable", enter_frac=0.667, gates={"status_ok": True, "quality": True, "yield_cover": True, "stable": False}),
    ]
    decay = {row["gate"]: row for row in decay_table(rows)}
    assert decay["asset_quality"]["eliminated"] == 1
    assert decay["yield_cover"]["entered"] == 4
    assert decay["yield_cover"]["eliminated"] == 2
    closest = closest_failures(rows, "yield_cover")
    assert [row["symbol"] for row in closest] == ["yield-near", "yield-far"]


def test_independent_cohort_reproduces_documented_shape_without_becoming_gate():
    base = {
        "pool": "id",
        "chain": "Base",
        "project": "aerodrome-slipstream",
        "symbol": "USDC-X",
        "tvlUsd": 200_000,
        "apyBase": 20.0,
        "apyReward": 0.0,
        "poolMeta": "CL50 - 0.05%",
        "stablecoin": True,
    }
    rows = independent_feasibility_cohort([base, dict(base, pool="low", apyBase=0.1)])
    assert [row["pool"] for row in rows] == ["id"]
    assert rows[0]["independent_il_tolerance_apr_pct"] > 0
    assert "not_entry_gate" in rows[0]["independent_semantics"]


def test_build_report_reads_sqlite_in_readonly_mode_and_splits_netcover(tmp_path):
    db = tmp_path / "scan.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE opportunity_scores (id INTEGER, as_of TEXT, score_json TEXT, accepted INTEGER)")
    records = [
        _row("missing", netcover=None, netcover_ratio=None, netcover_pass=False),
        _row("below", netcover=0.8, netcover_ratio=0.8, netcover_pass=False),
    ]
    for index, record in enumerate(records):
        connection.execute(
            "INSERT INTO opportunity_scores VALUES (?, ?, ?, ?)",
            (index, "2026-08-10T00:00:00+00:00", json.dumps(record), 0),
        )
    connection.commit()
    connection.close()
    report = build_report(db_path=db, stage1_records=records)
    assert report["accepted_recomputed"] == 0
    assert report["netcover_failures"] == {"missing_input": 1, "calculated_below_1": 1}
    assert all(not gate_bits(record)["netcover"] for record in records)
    markdown = render_markdown(report)
    assert "没有到达本闸后失败的池" in markdown


def test_build_report_can_pin_an_exact_scanner_snapshot(tmp_path):
    db = tmp_path / "scan.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE opportunity_scores (id INTEGER, as_of TEXT, score_json TEXT, accepted INTEGER)")
    connection.execute(
        "INSERT INTO opportunity_scores VALUES (?, ?, ?, ?)",
        (1, "earlier", json.dumps(_row("earlier")), 1),
    )
    connection.execute(
        "INSERT INTO opportunity_scores VALUES (?, ?, ?, ?)",
        (2, "later", json.dumps(_row("later", netcover_pass=False)), 0),
    )
    connection.commit()
    connection.close()

    report = build_report(db_path=db, stage1_records=[], scanner_as_of="earlier")
    assert report["source"]["scanner_as_of"] == "earlier"
    assert report["accepted_recomputed"] == 1
