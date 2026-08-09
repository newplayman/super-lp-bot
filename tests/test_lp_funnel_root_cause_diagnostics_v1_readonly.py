import json
import sqlite3

from scripts import lp_funnel_root_cause_diagnostics_v1_readonly as diag


class FakeRpc:
    def call(self, method, params):
        if method == "eth_blockNumber":
            return "0x123"
        if method == "eth_getCode":
            return "0x6000"
        data = params[0]["data"]
        if data == diag.TOKEN0_SELECTOR:
            return "0x" + "0" * 24 + "11" * 20
        if data == diag.TOKEN1_SELECTOR:
            return "0x" + "0" * 24 + "22" * 20
        if data == diag.SELECTOR_DECIMALS:
            return "0x" + format(18, "064x")
        if data == diag.SLOT0_SELECTOR:
            return "0x" + format(123, "064x") + "0" * 320
        if data == diag.LIQUIDITY_SELECTOR:
            return "0x" + format(456, "064x")
        if data == diag.FEE_SELECTOR:
            return "0x" + format(500, "064x")
        return "0x" + "0" * 64

    def health_snapshot(self):
        return {"state": "NORMAL"}


def _db(tmp_path):
    path = tmp_path / "scanner.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE opportunity_scores (id INTEGER PRIMARY KEY, as_of TEXT, score_json TEXT)"
    )
    base = {field: None for field in diag.NETCOVER_INPUT_FIELDS}
    resolved = dict(
        base, symbol="X-Y", project="aerodrome-slipstream", resolve_status="OK",
        status="OK", resolved_pool="0x" + "aa" * 20, token0="0x" + "11" * 20,
        token1="0x" + "22" * 20, dec0=18, dec1=18, fee_tier=.0005,
        tick_spacing=10, poolMeta="CL10 - 0.05%", underlyingTokens=["0x" + "11" * 20, "0x" + "22" * 20],
        swap_count=3, last_swap_price_token1_per_token0=2.0, last_swap_liquidity_raw=99,
    )
    unresolved = dict(
        base, symbol="A-B", project="aerodrome-slipstream", resolve_status="NOT_FOUND",
        status="NOT_FOUND", resolved_pool=None, fee_tier=.003, tick_spacing=200,
        poolMeta="CL200 - 0.3%", underlyingTokens=["0x" + "33" * 20, "0x" + "44" * 20],
        swap_count=0,
    )
    for i, row in enumerate((resolved, unresolved), 1):
        connection.execute(
            "INSERT INTO opportunity_scores VALUES (?,?,?)",
            (i, "2026-08-09T00:00:00+00:00", json.dumps(row)),
        )
    connection.commit()
    connection.close()
    return path


def test_collect_is_read_only_and_covers_resolved_and_not_found(tmp_path):
    path = _db(tmp_path)
    before = path.read_bytes()
    report = diag.collect(path, FakeRpc())
    assert path.read_bytes() == before
    assert len(report["records"]) == 2
    assert report["records"][0]["rpc_evidence"]["slot0"]["decoded_first_word_uint"] == 123
    assert report["records"][0]["rpc_evidence"]["liquidity"]["decoded_first_word_uint"] == 456
    assert report["records"][1]["classification"] == "POOL_NOT_IN_SUPPORTED_FACTORY"
    assert all(
        probe["decoded_address"] == diag.ZERO_ADDRESS
        for orders in report["records"][1]["rpc_evidence"]["initial_factory_spacing_probes"].values()
        for probe in orders
    )
    markdown = diag.render_markdown(report)
    assert "X-Y" in markdown and "A-B" in markdown and "SKIPPED_NO_POOL" in markdown
