from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import execution.base_m1_executor_v1 as executor


FACTORY = "0x1111111111111111111111111111111111111111"
WETH9 = "0x4200000000000000000000000000000000000006"


def _abi_address(address: str) -> str:
    return "0x" + address[2:].lower().rjust(64, "0")


class FakeDeploymentRpc:
    def __init__(self, *, code: str = "0x01", bad_factory: bool = False):
        self.code = code
        self.bad_factory = bad_factory
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_getCode":
            return self.code
        selector = params[0]["data"]
        if selector == "0xc45a0155":
            value = "0x2222222222222222222222222222222222222222" if self.bad_factory else FACTORY
            return _abi_address(value)
        if selector == "0x4aa4a4fc":
            return _abi_address(WETH9)
        raise AssertionError((method, params))


@pytest.fixture
def tiny_deployments(monkeypatch):
    expected = {
        address: {
            "code_bytes": 1,
            "code_sha256": hashlib.sha256(b"\x01").hexdigest(),
            "factory": FACTORY,
            "weth9": WETH9,
            "official_deployment": name,
        }
        for address, name in (
            ("0x1000000000000000000000000000000000000001", "initial"),
            ("0x1000000000000000000000000000000000000002", "gauge_caps"),
            ("0x1000000000000000000000000000000000000003", "gauges_v3"),
        )
    }
    monkeypatch.setattr(executor, "AERODROME_SLIPSTREAM_DEPLOYMENTS", expected)
    return expected


def test_all_three_npm_deployments_require_code_hash_factory_and_weth9(tiny_deployments):
    rpc = FakeDeploymentRpc()
    evidence = executor.verify_aerodrome_npm_deployments(rpc)
    assert len(evidence) == 3
    assert len(rpc.calls) == 9
    assert all(row["code_sha256"] == hashlib.sha256(b"\x01").hexdigest() for row in evidence)


@pytest.mark.parametrize(
    "rpc,match",
    [
        (FakeDeploymentRpc(code="0x"), "no runtime code"),
        (FakeDeploymentRpc(code="0x02"), "code_sha256"),
        (FakeDeploymentRpc(bad_factory=True), "factory"),
    ],
)
def test_npm_startup_verification_fails_closed(tiny_deployments, rpc, match):
    with pytest.raises(executor.PolicyRejected, match=match):
        executor.verify_aerodrome_npm_deployments(rpc)


def test_base_mainnet_executor_runs_deployment_check_during_construction(monkeypatch, tmp_path):
    observed = [{"address": "checked"}]
    calls = []

    def verify(rpc):
        calls.append(rpc)
        return observed

    rpc = object()
    monkeypatch.setattr(executor, "verify_aerodrome_npm_deployments", verify)
    instance = executor.BaseM1Executor(
        rpc=rpc,
        signer=object(),
        broadcaster=object(),
        policy=executor.ExecutionPolicy(),
        ledger=executor.Ledger(tmp_path / "ledger.jsonl"),
        wallet="0x1111111111111111111111111111111111111111",
        observed_chain_id=8453,
    )
    assert calls == [rpc]
    assert instance.deployment_evidence == observed


def test_external_dependency_ledger_records_free_readonly_degradable_urls():
    text = (Path(__file__).resolve().parents[1] / "docs/ops/external-readonly-dependencies.md").read_text()
    for host in ("api.dexscreener.com", "mainnet.base.org"):
        line = next(item for item in text.splitlines() if host in item)
        assert "只读" in line and "免费" in line and "可降级" in line
