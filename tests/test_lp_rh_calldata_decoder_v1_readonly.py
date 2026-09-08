import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')
import json
import subprocess
from pathlib import Path
import pytest
from scripts.lp_rh_calldata_decoder_v1_readonly import (
    SELECTORS,
    UNKNOWN_SELECTORS,
    check_amount_protection,
    check_approval,
    check_deadline,
    check_targets,
    decode_calldata,
    verify_intent,
)
ROOT = Path(__file__).resolve().parents[1]
TARGET = "0x" + "11" * 20
WALLET = "0x" + "22" * 20
OTHER = "0x" + "33" * 20
def word(value):
    if isinstance(value, str):
        value = int(value, 16) if value.startswith("0x") else int(value)
    return value.to_bytes(32, "big").hex()
def address(value):
    return "00" * 12 + value[2:]
def call(selector, values):
    return selector + "".join(values)
def approve(amount=7, spender=OTHER):
    return call("0x095ea7b3", [address(spender), word(amount)])
def transfer(recipient=WALLET):
    return call("0xa9059cbb", [address(recipient), word(3)])
def mint(amount0_min=0, amount1_min=9, recipient=WALLET, deadline=1100):
    values = [
        address(TARGET), address(OTHER), word(3000), word(0), word(10), word(0), word(9),
        word(amount0_min), word(amount1_min), address(recipient), word(deadline),
    ]
    return call("0x88316456", values)
def exact_input(amount_out_minimum=5, deadline=1100, recipient=WALLET):
    values = [
        address(TARGET), address(OTHER), word(3000), address(recipient), word(deadline),
        word(9), word(amount_out_minimum), word(0),
    ]
    return call("0x04e45aaf", values)
def collect(extra=None):
    values = [word(1), address(WALLET), word(2), word(3)]
    if extra is not None:
        values.append(word(extra))
    return call("0xfc6f7865", values)
def multicall(*calls):
    encoded = [bytes.fromhex(item[2:]) for item in calls]
    head_size = 32 + 32 * len(encoded)
    pieces = [word(32), word(len(encoded))]
    cursor = head_size
    tails = []
    for item in encoded:
        pieces.append(word(cursor))
        padded = item.hex() + "0" * ((32 - len(item) % 32) % 32) * 2
        tails.append(word(len(item)) + padded)
        cursor += 32 + ((len(item) + 31) // 32) * 32
    return "0xac9650d8" + "".join(pieces + tails)
def test_approve_decodes_address_and_amount():
    decoded = decode_calldata(approve(123, WALLET))
    assert decoded["status"] == "OK"
    assert decoded["selector"] == "0x095ea7b3"
    assert decoded["known"] is True
    assert decoded["raw_words"] == 2
    assert decoded["args"][0]["value"] == WALLET
    assert decoded["args"][1]["value"] == 123
def test_transfer_decodes_recipient():
    decoded = decode_calldata(transfer(WALLET))
    assert [item["name"] for item in decoded["args"]] == ["recipient", "amount"]
    assert decoded["args"][0]["value"] == WALLET
def test_short_calldata_is_malformed():
    decoded = decode_calldata("0x095ea7b3")
    assert decoded["status"] == "MALFORMED_CALLDATA"
def test_unaligned_calldata_is_malformed():
    decoded = decode_calldata("0x095ea7b3" + "00")
    assert decoded["status"] == "MALFORMED_CALLDATA"
def test_unknown_selector_is_reported_and_registered():
    selector = "0xdeadbeef"
    decoded = decode_calldata(selector)
    assert decoded["status"] == "UNKNOWN_SELECTOR"
    assert decoded["known"] is False
    assert selector in UNKNOWN_SELECTORS
def test_exact_input_single_layout():
    decoded = decode_calldata(exact_input())
    assert decoded["args"][6]["name"] == "amountOutMinimum"
    assert decoded["args"][6]["value"] == 5
    assert decoded["args"][4]["value"] == 1100
def test_mint_layout_has_both_minimums():
    decoded = decode_calldata(mint(4, 8))
    values = {item["name"]: item["value"] for item in decoded["args"]}
    assert values["amount0Min"] == 4
    assert values["amount1Min"] == 8
    assert values["recipient"] == WALLET
def test_increase_liquidity_decodes():
    data = call("0x219f5d17", [word(1), word(2), word(3), word(4), word(5), word(1100)])
    decoded = decode_calldata(data)
    assert decoded["status"] == "OK"
    assert decoded["args"][-1]["name"] == "deadline"
def test_decrease_liquidity_decodes():
    data = call("0x0c49ccbe", [word(1), word(2), word(0), word(4), word(1100)])
    decoded = decode_calldata(data)
    assert decoded["args"][1]["type"] == "uint128"
    assert decoded["args"][2]["value"] == 0
def test_collect_decodes_without_minimum_output():
    decoded = decode_calldata(collect())
    assert decoded["status"] == "OK"
    assert "amountOutMinimum" not in [item["name"] for item in decoded["args"]]
def test_burn_decodes_token_id():
    decoded = decode_calldata("0x42966c68" + word(42))
    assert decoded["args"][0]["value"] == 42
def test_multicall_recursively_decodes_two_children():
    decoded = decode_calldata(multicall(approve(1, WALLET), transfer(WALLET)))
    children = decoded["args"][0]["value"]
    assert len(children) == 2
    assert children[0]["selector"] == "0x095ea7b3"
    assert children[1]["args"][0]["value"] == WALLET
def test_multicall_child_target_outside_allowlist_is_named():
    decoded = decode_calldata(multicall(approve(1, WALLET), transfer(WALLET)))
    decoded["args"][0]["value"][1]["target"] = OTHER
    ok, reasons = check_targets(decoded, target=TARGET, allowlist={TARGET, WALLET})
    assert not ok
    assert any("SUBCALL_TARGET_NOT_ALLOWLISTED" in reason and "subcall[1]" in reason
               for reason in reasons)
def test_top_level_target_outside_allowlist_is_rejected():
    decoded = decode_calldata(approve(1, WALLET))
    ok, reasons = check_targets(decoded, target=OTHER, allowlist={TARGET, WALLET})
    assert not ok
    assert "TARGET_NOT_ALLOWLISTED" in reasons
def test_t48_recipient_outside_allowlist_is_rejected():
    decoded = decode_calldata(transfer(OTHER))
    ok, reasons = check_targets(decoded, target=TARGET, allowlist={TARGET, WALLET})
    assert not ok
    assert any("RECIPIENT_NOT_ALLOWLISTED" in reason for reason in reasons)
def test_self_wallet_recipient_is_allowed():
    decoded = decode_calldata(transfer(WALLET))
    decoded["self_wallet"] = WALLET
    assert check_targets(decoded, target=TARGET, allowlist={TARGET})[0]
def test_t50_zero_leg_is_legitimate():
    decoded = decode_calldata(mint(0, 9))
    ok, reasons = check_amount_protection(decoded, leg0_expected_zero=True,
                                           leg1_expected_zero=False)
    assert ok
    assert any(reason.startswith("LEGITIMATE_ZERO_LEG") for reason in reasons)
def test_t50_nonzero_leg_with_zero_minimum_is_rejected():
    decoded = decode_calldata(mint(0, 0))
    ok, reasons = check_amount_protection(decoded, leg0_expected_zero=True,
                                           leg1_expected_zero=False)
    assert not ok
    assert any(reason.startswith("MISSING_SLIPPAGE_PROTECTION") for reason in reasons)
def test_t50_swap_zero_minimum_is_rejected():
    decoded = decode_calldata(exact_input(0))
    ok, reasons = check_amount_protection(decoded, leg0_expected_zero=False,
                                           leg1_expected_zero=False)
    assert not ok
    assert any("MISSING_SLIPPAGE_PROTECTION" in reason for reason in reasons)
def test_t50_collect_fake_minimum_is_rejected():
    decoded = decode_calldata(collect(77))
    ok, reasons = check_amount_protection(decoded, leg0_expected_zero=False,
                                           leg1_expected_zero=False)
    assert not ok
    assert any(reason.startswith("FABRICATED_MIN_OUT_ON_COLLECT") for reason in reasons)
def test_deadline_missing():
    decoded = decode_calldata(mint())
    decoded["args"] = decoded["args"][:-1]
    assert check_deadline(decoded, now_unix=1000) == (False, "DEADLINE_MISSING")
def test_deadline_expired():
    decoded = decode_calldata(mint(deadline=1000))
    assert check_deadline(decoded, now_unix=1000) == (False, "DEADLINE_EXPIRED")
def test_deadline_too_far():
    decoded = decode_calldata(mint(deadline=1301))
    assert check_deadline(decoded, now_unix=1000) == (False, "DEADLINE_TOO_FAR")
def test_deadline_within_horizon():
    decoded = decode_calldata(mint(deadline=1300))
    assert check_deadline(decoded, now_unix=1000) == (True, "OK")
def test_unlimited_approval_is_forbidden():
    assert check_approval(decode_calldata(approve(2 ** 256 - 1))) == (
        False, "UNLIMITED_APPROVAL_FORBIDDEN")
def test_approval_at_2_to_255_is_forbidden():
    assert check_approval(decode_calldata(approve(2 ** 255))) == (
        False, "UNLIMITED_APPROVAL_FORBIDDEN")
def test_finite_approval_passes():
    assert check_approval(decode_calldata(approve(10))) == (True, "OK")
FULL_INTENT = {
    "chain_id": 1, "wallet_id": "wallet-1", "position_id": "position-1",
    "request_id": "request-1", "decision_id": "decision-1",
    "idempotency_key": "idem-1", "policy_hash": "policy-1",
    "code_version": "v1", "snapshot_hash": "snapshot-1",
    "calldata_hash": "calldata-1", "expires_at": 1100,
}
def test_verify_intent_accepts_complete_matching_metadata():
    decoded = decode_calldata(mint())
    decoded.update(FULL_INTENT)
    assert verify_intent(decoded, intent=FULL_INTENT) == (True, [])
@pytest.mark.parametrize("field", tuple(FULL_INTENT))
def test_verify_intent_rejects_each_missing_required_field(field):
    intent = dict(FULL_INTENT)
    intent.pop(field)
    ok, reasons = verify_intent(decode_calldata(mint()), intent=intent)
    assert not ok
    assert "INTENT_FIELD_MISSING:" + field in reasons
def test_verify_intent_rejects_mismatch():
    decoded = decode_calldata(mint())
    decoded.update(FULL_INTENT)
    bad = dict(FULL_INTENT, request_id="other-request")
    ok, reasons = verify_intent(decoded, intent=bad)
    assert not ok
    assert "INTENT_MISMATCH:request_id" in reasons
def test_source_has_no_forbidden_capability_names():
    source = (ROOT / "scripts" / "lp_rh_calldata_decoder_v1_readonly.py").read_text()
    for forbidden in ("import web3", "eth_account", "sign", "send_raw", "private_key"):
        assert forbidden not in source.lower()
def test_cli_writes_json_without_external_access(tmp_path):
    allowlist_path = tmp_path / "allowlist.json"
    intent_path = tmp_path / "intent.json"
    output_path = tmp_path / "out.json"
    allowlist_path.write_text(json.dumps([TARGET, WALLET]))
    intent_path.write_text(json.dumps(FULL_INTENT))
    command = [
        sys.executable, str(ROOT / "scripts" / "lp_rh_calldata_decoder_v1_readonly.py"),
        "--calldata", mint(), "--target", TARGET,
        "--allowlist-json", str(allowlist_path), "--intent-json", str(intent_path),
        "--out", str(output_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    result = json.loads(output_path.read_text())
    assert result["decoded"]["status"] == "OK"
