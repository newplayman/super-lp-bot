from pathlib import Path


SCRIPT = Path("/Users/bendu/lp-bot/v3/scripts/lp_bsc_pancakeswap_v3_precise_quote_v1_readonly.py")
REPORT_DIR = Path("/Users/bendu/lp-bot/v3/reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959")


def test_v1_script_is_readonly():
    text = SCRIPT.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction",
        "eth_sendtransaction",
        "signtransaction(",
        "private_key",
        "mnemonic",
        "--canary-mint",
    ]
    for token in banned:
        assert token not in text


def test_v1_final_verdict_flags():
    text = (REPORT_DIR / "LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json").read_text(encoding="utf-8")
    assert '"tiny_canary_allowed": "no"' in text
    assert '"edge_proven": "no"' in text
    assert '"recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT"' in text
