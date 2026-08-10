from __future__ import annotations

import pytest

from execution.base_m1_executor_v1 import (
    BASE_SEPOLIA_CHAIN_ID,
    ExecutionNetwork,
    PolicyRejected,
    assert_executor_chain_id,
)
from scripts.lp_base_sepolia_smoke_v1_readonly import dry_run, validate_config


def _config(**changes):
    config = {
        "network": "base_sepolia",
        "expected_chain_id": 84532,
        "rpc_url": "https://example.invalid",
        "dry_run_only": True,
        "signing_enabled": False,
        "broadcast_enabled": False,
        "live_trading": False,
        "contracts": {
            "weth9": "0x4200000000000000000000000000000000000006",
            "position_manager": None,
            "token0": None,
            "token1": None,
            "pool": None,
        },
    }
    config.update(changes)
    return config


def test_base_sepolia_chain_id_is_exact_and_mainnet_is_rejected():
    assert assert_executor_chain_id(ExecutionNetwork.BASE_SEPOLIA, 84532) == BASE_SEPOLIA_CHAIN_ID
    with pytest.raises(PolicyRejected, match="expected chain id 84532, observed 8453"):
        assert_executor_chain_id(ExecutionNetwork.BASE_SEPOLIA, 8453)
    with pytest.raises(PolicyRejected):
        assert_executor_chain_id(ExecutionNetwork.BASE_SEPOLIA, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"dry_run_only": False},
        {"signing_enabled": True},
        {"broadcast_enabled": True},
        {"live_trading": True},
        {"expected_chain_id": 8453},
    ],
)
def test_smoke_config_rejects_every_unsafe_flag(change):
    with pytest.raises(ValueError):
        validate_config(_config(**change))


def test_dry_run_uses_only_read_methods_and_never_signs_or_sends():
    calls = []
    def rpc(_url, method, params):
        calls.append((method, params))
        return {
            "eth_chainId": hex(84532),
            "eth_blockNumber": hex(123),
            "eth_getCode": "0x6000",
            "eth_call": "0x" + "0" * 63 + "1",
        }[method]
    report = dry_run(_config(), rpc_call=rpc)
    assert {method for method, _ in calls} == {"eth_chainId", "eth_blockNumber", "eth_getCode", "eth_call"}
    assert report["chain_id"] == 84532
    assert report["full_contract_simulation_ready"] is False
    assert report["safety"]["signed"] is False
    assert report["safety"]["broadcast_count"] == 0
    assert report["safety"]["eth_send_raw_transaction_calls"] == 0


def test_dry_run_refuses_mainnet_before_any_contract_simulation():
    calls = []
    def rpc(_url, method, _params):
        calls.append(method)
        return hex(8453)
    with pytest.raises(PolicyRejected, match="observed 8453"):
        dry_run(_config(), rpc_call=rpc)
    assert calls == ["eth_chainId"]
