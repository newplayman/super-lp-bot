from __future__ import annotations

from pathlib import Path
import json
import re
import importlib.util
import sys

SCRIPT_PATH = Path('/Users/bendu/lp-bot/v3/scripts/lp_evm_universe_expansion_design_v1_readonly.py')
REPORT_ROOT = Path('/Users/bendu/lp-bot/v3/reports/lp_evm_universe_expansion_design')


def _latest_report_dir() -> Path:
    dirs = sorted([p for p in REPORT_ROOT.iterdir() if p.is_dir() and re.fullmatch(r'\d{8}_\d{6}', p.name)])
    assert dirs, 'no report dir found'
    return dirs[-1]


def _load_module():
    spec = importlib.util.spec_from_file_location('lp_evm_universe_expansion_design_v1_readonly', SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bsc_pancake_v3_included_in_final_verdict():
    path = _latest_report_dir() / 'FINAL_VERDICT.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['bsc_pancakeswap_v3_included'] is True
    assert data['stage'] == 'LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1'


def test_solana_deferred_and_probe_disabled():
    data = json.loads((_latest_report_dir() / 'evm_universe_expansion_next_stage_decision.json').read_text(encoding='utf-8'))
    assert data['can_run_probe_now'] is False
    verdict = json.loads((_latest_report_dir() / 'FINAL_VERDICT.json').read_text(encoding='utf-8'))
    assert verdict['solana_deferred'] is True


def test_no_trading_or_signature_symbols_in_script():
    text = SCRIPT_PATH.read_text(encoding='utf-8').lower()
    for token in ['eth_sendrawtransaction', 'eth_sendtransaction', 'sign_transaction', 'build_transaction', 'send_transaction', 'swap', 'mint', 'increaseliquidity', 'decreaseliquidity', 'nonfungiblepositionmanager', 'collect', 'burn']:
        assert token not in text


def test_contract_map_from_official_and_schema_fields_exist():
    mod = _load_module()
    assert hasattr(mod, 'BSC_CONTRACTS')
    assert 'PancakeV3Factory' in mod.BSC_CONTRACTS
    assert 'QuoterV2' in mod.BSC_CONTRACTS
    design = json.loads((_latest_report_dir() / 'evm_universe_expansion_schema.json').read_text(encoding='utf-8'))
    fields_required = ['run_id', 'chain', 'chain_id', 'protocol', 'pool_type', 'factory_address', 'pool_address', 'fee_tier', 'quote_ready', 'tick_ready', 'cost_ready']
    names = {t['name']: t for t in design['tables']}
    for t in ['lp_evm_pool_universe_v1', 'lp_evm_pool_metadata_v1', 'lp_bsc_pancakeswap_v3_pool_candidates_v1', 'lp_evm_pool_discovery_run_v1']:
        assert t in names
    for f in fields_required:
        assert f in names['lp_evm_pool_universe_v1']['fields']


def test_metadata_unknown_not_guessed():
    policy = json.loads((_latest_report_dir() / 'metadata_gap_policy.json').read_text(encoding='utf-8'))
    assert any('不猜 token symbol' in x or 'metadata_confidence' in x for x in policy['rules'])
    assert '所有 unknown 不自动补齐' in policy['rules'][-1] or any('unknown 不自动补齐' in x for x in policy['rules'])


def test_allowed_next_stage_only():
    verdict = json.loads((_latest_report_dir() / 'FINAL_VERDICT.json').read_text(encoding='utf-8'))
    allowed = {
        'LP_BSC_PANCAKESWAP_V3_UNIVERSE_DISCOVERY_V1',
        'LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1',
        'LP_EVM_UNIVERSE_METADATA_PIPELINE_V1',
        'LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1',
        'STOP_LP_RESEARCH_NOW',
    }
    assert verdict['recommended_next_stage'] in allowed
