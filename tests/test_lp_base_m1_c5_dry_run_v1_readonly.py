from pathlib import Path

from scripts.lp_base_m1_c5_dry_run_v1_readonly import encode_multicall


def test_multicall_encoder_matches_known_selector_and_dynamic_array_shape():
    data = encode_multicall(["0x1234", "0xabcdef"])
    assert data.startswith("0xac9650d8" + f"{32:064x}" + f"{2:064x}")
    assert "1234" in data and "abcdef" in data


def test_c5_source_has_no_signing_or_broadcast_rpc_method():
    source = (Path(__file__).parents[1] / "scripts/lp_base_m1_c5_dry_run_v1_readonly.py").read_text()
    forbidden = ("eth_sendRawTransaction", "eth_sendTransaction", "PRIVATE_KEY", "MNEMONIC", "cast send")
    assert all(item not in source for item in forbidden)
    assert '"broadcast_count": 0' in source
