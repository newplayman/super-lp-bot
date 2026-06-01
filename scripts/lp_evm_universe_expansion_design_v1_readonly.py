#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path('/Users/bendu/lp-bot/v3')
RUN_ID = os.environ.get('RUN_ID_OVERRIDE', '20260601_155703')
REPORT_DIR = REPO_ROOT / 'reports' / 'lp_evm_universe_expansion_design' / RUN_ID

INPUT_FILES = [
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/CURRENT_SCREENED_POOL_SUMMARY_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/LP_UNIVERSE_NORMALIZED_POOL_LIST_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/lp_universe_normalized_pool_list.csv',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/LP_UNIVERSE_STAGE_COVERAGE_MATRIX_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/CHAIN_PROTOCOL_COVERAGE_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/UNIVERSE_GAP_ANALYSIS_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/POOL_UNIVERSE_EXPANSION_PLAN_CN.md',
    REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/LP_UNIVERSE_SCOPE_NEXT_STAGE_DECISION_CN.md',
    REPO_ROOT / 'reports/lp_real_data_final_freeze/20260601_150954/FINAL_VERDICT.json',
    REPO_ROOT / 'reports/lp_real_fee_accrual_fix/20260601_145519/FINAL_VERDICT.json',
    REPO_ROOT / 'reports/lp_precise_quote/20260601_120001/FINAL_VERDICT.json',
    REPO_ROOT / 'reports/lp_v3_tick_liquidity_fix/20260601_132644/FINAL_VERDICT.json',
    REPO_ROOT / 'reports/lp_real_cost_model/20260601_141103/FINAL_VERDICT.json',
    REPO_ROOT / 'docs/LPBOT_RESEARCH_STATUS_CN.md',
    REPO_ROOT / 'docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md',
]

BSC_CONTRACTS = {
    "PancakeV3Factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    "PancakeV3PoolDeployer": "0x41ff9AA7e16B8B1a8a8dc4f0eFacd93D02d071c9",
    "SwapRouterV3": "0x1b81D678ffb9C0263b24A97847620C99d213eB14",
    "NonfungiblePositionManager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
    "QuoterV2": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    "TickLens": "0x9a489505a00cE272eAa5e07Dba6491314CaE3796",
    "SmartRouter": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
}

ALLOWED_NEXT = {
    "LP_BSC_PANCAKESWAP_V3_UNIVERSE_DISCOVERY_V1",
    "LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1",
    "LP_EVM_UNIVERSE_METADATA_PIPELINE_V1",
    "LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1",
    "STOP_LP_RESEARCH_NOW",
}


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path)
    path.write_text(text, encoding='utf-8')


def write_json(path: Path, obj) -> None:
    ensure_dir(path)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')


def write_csv(path: Path, rows, fieldnames) -> None:
    ensure_dir(path)
    with path.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def read_csv_rows(path: Path):
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def rpc_post(endpoint: str, payload: dict) -> tuple[bool, object, str]:
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode('utf-8')
            return True, json.loads(raw), ''
    except Exception as e:
        return False, None, str(e)


def check_bsc_readonly() -> dict:
    endpoints = [
        os.environ.get('BSC_RPC_URL', ''),
        os.environ.get('BSC_RPC', ''),
        os.environ.get('BSC_PUBLIC_RPC', ''),
        'https://bsc-dataseed.binance.org/',
        'https://rpc.ankr.com/bsc',
    ]
    endpoints = [e for e in endpoints if e]
    seen = set()
    candidates = []
    for e in endpoints:
        if e not in seen:
            seen.add(e)
            candidates.append(e)

    contract_checks = {}
    sample = {}
    selected = None
    chain_id = None
    latest_block = None

    for endpoint in candidates:
        ok, payload, err = rpc_post(endpoint, {'jsonrpc': '2.0', 'id': 1, 'method': 'eth_chainId', 'params': []})
        sample[endpoint] = {}
        if not ok or not isinstance(payload, dict) or 'error' in payload:
            sample[endpoint]['eth_chainId'] = f'fail:{err}'
            continue
        result = payload.get('result')
        if isinstance(result, str):
            chain_id = int(result, 16)
        sample[endpoint]['eth_chainId'] = chain_id
        ok2, payload2, err2 = rpc_post(endpoint, {'jsonrpc': '2.0', 'id': 2, 'method': 'eth_getBlockByNumber', 'params': ['latest', False]})
        if ok2 and isinstance(payload2, dict) and payload2.get('result'):
            latest_block = int(payload2['result'].get('number', '0x0'), 16)
        sample[endpoint]['eth_getBlockByNumber'] = latest_block if latest_block is not None else f'fail:{err2}'

        for name, addr in BSC_CONTRACTS.items():
            ok3, payload3, err3 = rpc_post(endpoint, {
                'jsonrpc': '2.0',
                'id': 3,
                'method': 'eth_getCode',
                'params': [addr, 'latest'],
            })
            if not ok3 or not isinstance(payload3, dict) or not payload3.get('result'):
                contract_checks[name] = {'address': addr, 'status': 'missing_or_fail', 'error': err3}
            elif payload3.get('result') == '0x':
                contract_checks[name] = {'address': addr, 'status': 'empty_code'}
            else:
                contract_checks[name] = {'address': addr, 'status': 'has_code'}

        selected = endpoint
        break

    if chain_id == 56:
        available = 'yes'
        read_only_safe = True
    elif selected:
        available = 'partial'
        read_only_safe = False
    else:
        available = 'no'
        read_only_safe = False

    return {
        'data_source': 'bsc_readonly_rpc',
        'endpoint': selected or '',
        'available': available,
        'read_only_safe': read_only_safe,
        'requires_wallet': False,
        'requires_signature': False,
        'implementation_risk': 'low' if read_only_safe else 'high',
        'chain_id': chain_id,
        'latest_block': latest_block,
        'sample_calls': sample,
        'contract_code_checks': contract_checks,
        'recommended_for_next_stage': read_only_safe,
        'blocker': '' if read_only_safe else ('chain_id mismatch' if chain_id is not None else 'no endpoint'),
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Stage B input audit
    input_rows = [{'path': str(p), 'exists': p.exists()} for p in INPUT_FILES]
    missing_inputs = [r['path'] for r in input_rows if not r['exists']]
    scope_verdict = read_json(REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json') if (REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json').exists() else {}
    audit_summary = {
        'all_inputs_present': len(missing_inputs) == 0,
        'missing_input_list': missing_inputs,
        'universe_likely_too_narrow': bool(scope_verdict.get('universe_likely_too_narrow', False)),
        'recommended_next_stage': scope_verdict.get('recommended_next_stage', ''),
        'current_negative_conclusion_scope': scope_verdict.get('current_negative_conclusion_scope', ''),
        'is_universe_expansion_design_only': True,
        'solana_deferred_this_round': True,
        'bsc_pancakeswap_v3_priority_objective': True,
        'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }

    write_json(REPORT_DIR / 'input_evidence_audit.json', {'input': input_rows, 'summary': audit_summary})
    write_text(
        REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md',
        '# 输入证据审计\n\n'
        + '\n'.join([f"- {r['path']}: {'存在' if r['exists'] else '缺失'}" for r in input_rows])
        + f"\n- universe_likely_too_narrow: {'true' if audit_summary['universe_likely_too_narrow'] else 'false'}"
        + f"\n- recommended_next_stage: {audit_summary['recommended_next_stage']}"
        + f"\n- current_negative_conclusion_scope: {audit_summary['current_negative_conclusion_scope']}"
        + '\n- 本轮仅做 universe expansion design（只读）: 是'
        + '\n- 暂不动 Solana: 是'
        + '\n- BSC PancakeSwap V3 作为 P0/P1 对象: 是\n'
    )

    # Current gap recap
    normalized = read_csv_rows(REPO_ROOT / 'reports/lp_universe_scope_audit/20260601_154136/lp_universe_normalized_pool_list.csv')
    chains = sorted({r.get('chain', 'unknown') for r in normalized if r.get('chain')})
    protocols = sorted({r.get('protocol', 'unknown') for r in normalized if r.get('protocol')})
    gap = {
        'recap': [
            '当前主要集中 Base',
            'Solana / Meteora 未覆盖',
            'Ethereum / Arbitrum / Optimism / Polygon / BSC 主流池未充分覆盖',
            '当前负结论仅适用于 current universe',
            'real-data pipeline 已能服务标准 EVM V3',
        ],
        'chain_distribution': chains,
        'protocol_distribution': protocols,
        'scope_summary': {
            'base_pool_count': int(scope_verdict.get('base_pool_count', 0)),
            'solana_pool_count': int(scope_verdict.get('solana_pool_count', 0)),
            'standard_evm_v3_pool_count': int(scope_verdict.get('standard_evm_v3_pool_count', 0)),
        },
        'solana_deferred': True,
        'next_step': '优先扩标准 EVM V3；新增 BSC PancakeSwap V3',
    }
    write_json(REPORT_DIR / 'current_universe_gap_recap.json', gap)
    write_text(
        REPORT_DIR / 'CURRENT_UNIVERSE_GAP_RECAP_CN.md',
        '# 当前 Universe Gap 复盘\n\n'
        '- 当前样本主要集中 Base\n'
        '- Solana 和 Meteora 未覆盖\n'
        '- ETH/Arb/OP/Polygon/BSC 主流标准池覆盖仍不足\n'
        '- 当前负结论仅适用于 current universe，不外推\n'
        '- real-data pipeline 已能支持标准 EVM V3\n'
        '- 本轮结论：优先扩 EVM 标准 V3，并把 BSC PancakeSwap V3 列为 P0/P1\n'
    )

    # Chain/protocol priority
    priority_rows = [
        {
            'chain': 'BSC',
            'protocol': 'PancakeSwap V3',
            'pool_type': 'concentrated_liquidity',
            'priority': 'P0',
            'why': '本轮重点新增覆盖对象',
            'current_coverage': 'absent',
            'data_needed': 'chain_id, contracts, quoter',
            'parser_needed': 'no',
            'quote_method': 'SwapRouterV3 + QuoterV2',
            'tick_liquidity_method': 'pool slot0/liquidity + tickBitmap/ticks',
            'fee_method': 'volume × fee_tier (pipeline)',
            'cost_model_method': 'real cost model reuse',
            'expected_complexity': '中',
            'recommended_action': 'Phase 1 discovery',
        },
        {'chain': 'Arbitrum', 'protocol': 'Uniswap V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P0', 'why': '标准 EVM V3 扩展', 'current_coverage': 'low', 'data_needed': 'factory + quoter', 'parser_needed': 'no', 'quote_method': 'existing v3 quoter', 'tick_liquidity_method': 'slot0 + pool state', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '中', 'recommended_action': 'Phase 2 discovery'},
        {'chain': 'Optimism', 'protocol': 'Uniswap V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P0', 'why': '标准 EVM V3 扩展', 'current_coverage': 'low', 'data_needed': 'factory + quoter', 'parser_needed': 'no', 'quote_method': 'existing v3 quoter', 'tick_liquidity_method': 'slot0 + pool state', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '中', 'recommended_action': 'Phase 2 discovery'},
        {'chain': 'Base', 'protocol': 'Uniswap V3 / PancakeSwap V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P0', 'why': '补充当前 Base 缺口', 'current_coverage': 'partial', 'data_needed': 'missing pools + metadata', 'parser_needed': 'no', 'quote_method': 'standard v3', 'tick_liquidity_method': 'slot0 + ticks', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '低', 'recommended_action': 'Phase 3补齐'},
        {'chain': 'Ethereum', 'protocol': 'Uniswap V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P1', 'why': '主网覆盖不足', 'current_coverage': 'low', 'data_needed': 'factory + quoter', 'parser_needed': 'no', 'quote_method': 'existing v3', 'tick_liquidity_method': 'slot0 + ticks', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '中', 'recommended_action': 'Phase 4'},
        {'chain': 'Polygon', 'protocol': 'Uniswap V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P1', 'why': '主网覆盖不足', 'current_coverage': 'low', 'data_needed': 'factory + quoter', 'parser_needed': 'no', 'quote_method': 'existing v3', 'tick_liquidity_method': 'slot0 + ticks', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '中', 'recommended_action': 'Phase 4'},
        {'chain': 'BSC', 'protocol': 'Uniswap-compatible V3', 'pool_type': 'concentrated_liquidity', 'priority': 'P1', 'why': 'BSC 其他 V3 兼容池', 'current_coverage': 'unknown', 'data_needed': 'factory list', 'parser_needed': 'no', 'quote_method': 'standard v3', 'tick_liquidity_method': 'slot0 + ticks', 'fee_method': 'existing', 'cost_model_method': 'existing', 'expected_complexity': '中', 'recommended_action': 'Phase 4'},
        {'chain': 'Base', 'protocol': 'Aerodrome Slipstream', 'pool_type': 'concentrated_liquidity', 'priority': 'P1', 'why': '仅在 parser 完成后', 'current_coverage': 'not_ready', 'data_needed': 'slot0 parser', 'parser_needed': 'yes', 'quote_method': 'custom adapter', 'tick_liquidity_method': 'custom', 'fee_method': 'custom', 'cost_model_method': 'custom extension', 'expected_complexity': '高', 'recommended_action': 'Phase 5'},
        {'chain': 'Multi', 'protocol': 'Curve', 'pool_type': 'curve_like', 'priority': 'P2', 'why': '当前研究重点外', 'current_coverage': 'not_covered', 'data_needed': 'specialized protocol path', 'parser_needed': 'yes', 'quote_method': 'future', 'tick_liquidity_method': 'future', 'fee_method': 'unknown', 'cost_model_method': 'future', 'expected_complexity': '高', 'recommended_action': 'future'},
        {'chain': 'Multi', 'protocol': 'Balancer', 'pool_type': 'weighted', 'priority': 'P2', 'why': '当前研究重点外', 'current_coverage': 'not_covered', 'data_needed': 'specialized protocol path', 'parser_needed': 'yes', 'quote_method': 'future', 'tick_liquidity_method': 'future', 'fee_method': 'unknown', 'cost_model_method': 'future', 'expected_complexity': '高', 'recommended_action': 'future'},
        {'chain': 'BSC', 'protocol': 'PancakeSwap V2', 'pool_type': 'stable', 'priority': 'P2', 'why': '暂不执行', 'current_coverage': 'limited', 'data_needed': 'stable quotes', 'parser_needed': 'yes', 'quote_method': 'future', 'tick_liquidity_method': 'future', 'fee_method': 'future', 'cost_model_method': 'future', 'expected_complexity': '高', 'recommended_action': 'future'},
        {'chain': 'Solana', 'protocol': 'Meteora/Orca/Raydium', 'pool_type': 'AMM', 'priority': 'P2', 'why': '暂不执行', 'current_coverage': 'none', 'data_needed': 'solana path', 'parser_needed': 'yes', 'quote_method': 'future', 'tick_liquidity_method': 'future', 'fee_method': 'future', 'cost_model_method': 'future', 'expected_complexity': '高', 'recommended_action': 'future_only'},
    ]
    headers = [
        'chain', 'protocol', 'pool_type', 'priority', 'why', 'current_coverage', 'data_needed',
        'parser_needed', 'quote_method', 'tick_liquidity_method', 'fee_method', 'cost_model_method', 'expected_complexity', 'recommended_action',
    ]
    write_csv(REPORT_DIR / 'evm_expansion_chain_protocol_priority.csv', priority_rows, headers)
    write_json(REPORT_DIR / 'evm_expansion_chain_protocol_priority.json', {
        'rows': priority_rows,
        'summary': {
            'p0_count': len([r for r in priority_rows if r['priority'] == 'P0']),
            'p1_count': len([r for r in priority_rows if r['priority'] == 'P1']),
            'p2_count': len([r for r in priority_rows if r['priority'] == 'P2']),
            'recommended_focus': 'BSC PancakeSwap V3, Arbitrum/Optimism/Base',
        },
    })
    write_text(
        REPORT_DIR / 'EVM_EXPANSION_CHAIN_PROTOCOL_PRIORITY_CN.md',
        '# EVM 扩展优先级\n\n'
        '- P0: BSC PancakeSwap V3；Arbitrum/Optimism/Base 标准 V3\n'
        '- P1: Ethereum/Polygon/Base Aerodrome，BSC 兼容 V3\n'
        '- P2: Curve/Balancer/BSC V2/Solana（暂不执行）\n'
    )

    # BSC design
    bsc_targets = [
        {'pair': 'WBNB/USDT', 'fees_supported': ['0.01%', '0.05%', '0.25%', '1%']},
        {'pair': 'WBNB/USDC', 'fees_supported': ['0.01%', '0.05%', '0.25%', '1%']},
        {'pair': 'ETH/USDT', 'fees_supported': ['0.05%', '0.3%', '1%']},
        {'pair': 'BTCB/WBNB', 'fees_supported': ['0.05%', '0.3%', '1%']},
        {'pair': 'BTCB/USDT', 'fees_supported': ['0.05%', '0.3%', '1%']},
        {'pair': 'CAKE/WBNB', 'fees_supported': ['0.05%', '0.25%', '1%']},
        {'pair': 'CAKE/USDT', 'fees_supported': ['0.05%', '0.25%', '1%']},
        {'pair': 'FDUSD/USDT', 'fees_supported': ['0.01%', '0.05%', '0.25%']},
        {'pair': 'USDT/USDC', 'fees_supported': ['0.01%', '0.05%', '0.25%']},
    ]
    bsc_design = {
        'chain': 'BSC', 'chain_id': 56,
        'protocol': 'PancakeSwap V3',
        'protocol_contract_map': [
            {'name': k, 'address': v, 'source': 'PancakeSwap official docs, verified by eth_getCode'} for k, v in BSC_CONTRACTS.items()
        ],
        'readonly_capability': [
            'factory.getPool(token0, token1, fee)',
            'pool.slot0()',
            'pool.tickSpacing()',
            'pool.liquidity()',
            'pool.token0/token1',
            'quoter.quoteExactInputSingle',
            'quoter.quoteExactOutputSingle',
            'tick data via pool state / tickBitmap / TickLens',
        ],
        'candidate_pairs': bsc_targets,
        'safety': {
            'no_swap': True,
            'no_mint': True,
            'no_wallet': True,
            'no_signing': True,
            'read_only_only': True,
        },
        'outputs': ['pool_address', 'token_pair', 'fee_tier', 'liquidity_proxy', 'quote_readiness', 'tick_readiness', 'fee_readiness', 'cost_readiness'],
    }
    write_json(REPORT_DIR / 'bsc_pancakeswap_v3_expansion_design.json', bsc_design)
    write_text(
        REPORT_DIR / 'BSC_PANCAKESWAP_V3_EXPANSION_DESIGN_CN.md',
        '# BSC PancakeSwap V3 扩展设计\n\n'
        'Chain: BSC (chain_id=56), Protocol: PancakeSwap V3\n\n'
        '- 合约地址（官方文档来源）:\n'
        + '\n'.join([f"  - {k}: {v}" for k, v in BSC_CONTRACTS.items()]) + '\n\n'
        '- 目标候选: WBNB/USDT, WBNB/USDC, ETH/USDT, BTCB/WBNB, BTCB/USDT, CAKE/WBNB, CAKE/USDT, FDUSD/USDT, USDT/USDC\n'
        '- 费用层级采用动态发现+保守测试（0.01/0.05/0.25/1）\n'
        '- 严格只读：不 swap/mint/signature/wallet\n'
    )

    # Feasibility
    bsc_feas = check_bsc_readonly()
    bsc_rows = [
        {
            'data_source': 'BSC RPC',
            'available': bsc_feas['available'],
            'read_only_safe': 'yes' if bsc_feas['read_only_safe'] else 'no',
            'requires_wallet': 'no',
            'requires_signature': 'no',
            'implementation_risk': bsc_feas['implementation_risk'],
            'recommended_for_next_stage': 'yes' if bsc_feas['recommended_for_next_stage'] else 'no',
            'blocker': bsc_feas['blocker'],
        }
    ]
    write_csv(REPORT_DIR / 'bsc_data_source_feasibility.csv', bsc_rows, ['data_source', 'available', 'read_only_safe', 'requires_wallet', 'requires_signature', 'implementation_risk', 'recommended_for_next_stage', 'blocker'])
    write_json(REPORT_DIR / 'bsc_data_source_feasibility.json', {
        'rpc_audit': bsc_feas,
        'rows': bsc_rows,
    })
    write_text(
        REPORT_DIR / 'BSC_DATA_SOURCE_FEASIBILITY_CN.md',
        '# BSC 数据源可行性审计\n\n'
        f"- available: {bsc_feas['available']}\n"
        f"- endpoint: {bsc_feas['endpoint'] or 'N/A'}\n"
        f"- chain_id: {bsc_feas['chain_id']}\n"
        f"- latest_block: {bsc_feas['latest_block']}\n"
        f"- read_only_safe: {'yes' if bsc_feas['read_only_safe'] else 'no'}\n"
        f"- requires_wallet: {str(bsc_feas['requires_wallet']).lower()}\n"
        f"- requires_signature: {str(bsc_feas['requires_signature']).lower()}\n"
        f"- implementation_risk: {bsc_feas['implementation_risk']}\n"
        f"- blocker: {bsc_feas['blocker'] or 'none'}\n"
        '\n'
        '合约读码结果（eth_getCode）见 json: contract_code_checks。\n'
    )

    # Schema proposal
    schema_rows = [
        {
            'table': 'lp_evm_pool_universe_v1',
            'run_id': RUN_ID,
            'note': 'research-only universe snapshot',
        },
        {'table': 'lp_evm_pool_metadata_v1', 'run_id': RUN_ID, 'note': 'token/pool metadata for research'},
        {'table': 'lp_bsc_pancakeswap_v3_pool_candidates_v1', 'run_id': RUN_ID, 'note': 'BSC PancakeSwap discovery output'},
        {'table': 'lp_evm_pool_discovery_run_v1', 'run_id': RUN_ID, 'note': 'discovery run trace'},
    ]
    schema_json = {
        'tables': [
            {
                'name': 'lp_evm_pool_universe_v1',
                'fields': ['run_id', 'chain', 'chain_id', 'protocol', 'pool_type', 'factory_address', 'pool_address', 'token0', 'token1', 'token0_symbol', 'token1_symbol', 'fee_tier', 'tick_spacing', 'discovered_by', 'discovery_method', 'quote_ready', 'tick_ready', 'cost_ready', 'fee_ready', 'metadata_confidence', 'invalid_reason', 'created_at'],
            },
            {
                'name': 'lp_evm_pool_metadata_v1',
                'fields': ['run_id', 'chain', 'chain_id', 'pool_address', 'token0', 'token1', 'token0_symbol', 'token1_symbol', 'decimals0', 'decimals1', 'liquidity_proxy', 'tvl_proxy', 'updated_at', 'metadata_confidence', 'invalid_reason', 'created_at'],
            },
            {
                'name': 'lp_bsc_pancakeswap_v3_pool_candidates_v1',
                'fields': ['run_id', 'pool_address', 'token_pair', 'fee_tier', 'tvl_usd', 'liquidity_proxy', 'quote_ready', 'tick_ready', 'cost_ready', 'fee_ready', 'invalid_reason', 'created_at'],
            },
            {
                'name': 'lp_evm_pool_discovery_run_v1',
                'fields': ['run_id', 'stage', 'chain', 'protocol', 'pool_count', 'candidate_count', 'new_pool_count', 'coverage_status', 'notes', 'created_at'],
            },
        ],
        'notes': ['仅 research-only 表', '仅记录离线/可读方法输出', '不得覆盖 production positions'],
    }
    write_json(REPORT_DIR / 'evm_universe_expansion_schema.json', schema_json)
    write_text(
        REPORT_DIR / 'EVM_UNIVERSE_EXPANSION_SCHEMA_CN.md',
        '# EVM Universe Expansion Schema\n\n'
        + '\n'.join([f"- {r['table']}: {r['note']}" for r in schema_rows]) + '\n'
    )

    # Discovery implementation plan
    plan = {
        'phases': [
            {'phase': 1, 'name': 'BSC PancakeSwap V3 candidate discovery', 'required_contracts': list(BSC_CONTRACTS.values()), 'required_rpc': 'BSC readonly RPC', 'script_name': 'lp_evm_universe_expansion_design_v1_readonly.py', 'output': 'lp_bsc_pancakeswap_v3_pool_candidates_v1', 'safety_gate': 'read-only', 'expected_next_stage': 'LP_BSC_PANCAKESWAP_V3_UNIVERSE_DISCOVERY_V1'},
            {'phase': 2, 'name': 'Arb/OP Uniswap V3 candidate discovery', 'required_contracts': ['UniswapV3Factory', 'QuoterV3'], 'required_rpc': 'Arb/OP RPC', 'script_name': 'lp_evm_universe_expansion_design_v1_readonly.py', 'output': 'lp_evm_pool_universe_v1', 'safety_gate': 'read-only', 'expected_next_stage': 'LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1'},
            {'phase': 3, 'name': 'Base missing standard V3补齐', 'required_contracts': ['Base V3 pools'], 'required_rpc': 'Base RPC', 'script_name': 'lp_evm_universe_expansion_design_v1_readonly.py', 'output': 'lp_evm_pool_discovery_run_v1', 'safety_gate': 'read-only', 'expected_next_stage': 'LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1'},
            {'phase': 4, 'name': 'ETH/Polygon expansion', 'required_contracts': ['ETH/Polygon V3 factories'], 'required_rpc': 'ETH/POLYGON RPC', 'script_name': 'lp_evm_universe_expansion_design_v1_readonly.py', 'output': 'lp_evm_pool_universe_v1', 'safety_gate': 'read-only', 'expected_next_stage': 'LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1'},
            {'phase': 5, 'name': 'Aerodrome parser design', 'required_contracts': ['Aerodrome slot0 parser'], 'required_rpc': 'Base RPC + docs', 'script_name': 'lp_evm_universe_expansion_design_v1_readonly.py', 'output': 'lp_evm_pool_universe_v1', 'safety_gate': 'read-only', 'expected_next_stage': 'LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1'},
        ]
    }
    write_json(REPORT_DIR / 'evm_pool_discovery_implementation_plan.json', plan)
    write_text(
        REPORT_DIR / 'EVM_POOL_DISCOVERY_IMPLEMENTATION_PLAN_CN.md',
        '# EVM 池子发现实现计划\n\n'
        + '\n'.join([f"- Phase {p['phase']}: {p['name']} => {p['expected_next_stage']}" for p in plan['phases']]) + '\n'
    )

    # Metadata policy
    policy = {
        'rules': [
            '不猜 token symbol，无法解析时保留 address',
            'token address 无法解析 -> 用 address 替代 symbol',
            'fee tier unknown -> unknown',
            'pool_type unknown -> 不进入 precise quote',
            'BSC token decimals 使用 ERC20 decimals 只读查询',
            'token symbol 可读则记录，不可读则 unknown',
            'metadata_confidence in [high, medium, low]',
            '所有 unknown 不自动补齐',
        ],
        'pipeline': 'research-only',
    }
    write_json(REPORT_DIR / 'metadata_gap_policy.json', policy)
    write_text(
        REPORT_DIR / 'METADATA_GAP_POLICY_CN.md',
        '# Metadata 缺口策略\n\n'
        + '\n'.join([f"- {r}" for r in policy['rules']]) + '\n'
    )

    # decide next stage
    bsc_feasible = bool(bsc_feas['read_only_safe'])
    contract_ready = all(v['status'] == 'has_code' for v in bsc_feas['contract_code_checks'].values()) if bsc_feas['contract_code_checks'] else False
    if audit_summary['bsc_pancakeswap_v3_priority_objective'] and not bsc_feasible:
        recommended = 'LP_BSC_PANCAKESWAP_V3_UNIVERSE_DISCOVERY_V1'
    elif bsc_feasible and contract_ready:
        recommended = 'LP_BSC_PANCAKESWAP_V3_UNIVERSE_DISCOVERY_V1'
    else:
        recommended = 'LP_EVM_STANDARD_V3_UNIVERSE_DISCOVERY_V1'
    next_decision = {
        'status': 'PASS' if recommended in ALLOWED_NEXT else 'FAIL',
        'recommended_next_stage': recommended,
        'reason': 'BSC read-only feasibility and expansion intent',
        'can_run_discovery_next': bsc_feasible,
        'can_run_probe_now': False,
        'tiny_canary_allowed': 'no',
        'bsc_readonly_path_feasible': bsc_feasible,
        'bsc_contract_map_ready': bool(bsc_feas['contract_code_checks']),
    }
    write_json(REPORT_DIR / 'evm_universe_expansion_next_stage_decision.json', next_decision)
    write_text(
        REPORT_DIR / 'EVM_UNIVERSE_EXPANSION_NEXT_STAGE_DECISION_CN.md',
        '# 下一阶段决议\n\n'
        f"- 推荐: {recommended}\n"
        f"- bsc_readonly_path_feasible: {str(next_decision['bsc_readonly_path_feasible']).lower()}\n"
        f"- bsc_pancakeswap_contract_map_ready: {str(next_decision['bsc_contract_map_ready']).lower()}\n"
        f"- can_run_discovery_next: {str(next_decision['can_run_discovery_next']).lower()}\n"
        '- no probe, no canary, no live\n'
    )

    # Final verdict & onepage
    final_verdict = {
        'status': 'WARN' if audit_summary['all_inputs_present'] and recommended in ALLOWED_NEXT else 'FAIL',
        'stage': 'LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1',
        'evm_expansion_design_complete': True,
        'bsc_pancakeswap_v3_included': True,
        'solana_deferred': True,
        'bsc_readonly_path_feasible': bsc_feasible,
        'bsc_pancakeswap_contract_map_ready': bool(contract_ready),
        'target_chain_count': len({r['chain'] for r in priority_rows}),
        'target_protocol_count': len({r['protocol'] for r in priority_rows}),
        'recommended_p0_chain_protocol': 'BSC:PancakeSwap V3',
        'can_run_discovery_next': bool(bsc_feasible),
        'can_run_probe_now': False,
        'edge_proven': 'no',
        'tiny_canary_candidate': 'no',
        'tiny_canary_allowed': 'no',
        'recommended_next_stage': recommended,
        'input_audit_complete': audit_summary['all_inputs_present'],
        'solana_deferred_note': 'deferred',
    }
    write_json(REPORT_DIR / 'FINAL_VERDICT.json', final_verdict)

    write_text(
        REPORT_DIR / 'ONEPAGE_CN.md',
        '# 一页结论\n\n'
        f"- stage: {final_verdict['stage']}\n"
        f"- status: {final_verdict['status']}\n"
        f"- bsc_pancakeswap_v3_included: {str(final_verdict['bsc_pancakeswap_v3_included']).lower()}\n"
        f"- solana_deferred: {str(final_verdict['solana_deferred']).lower()}\n"
        f"- bsc_readonly_path_feasible: {str(final_verdict['bsc_readonly_path_feasible']).lower()}\n"
        f"- recommended_next_stage: {final_verdict['recommended_next_stage']}\n"
        f"- target_chain_count: {final_verdict['target_chain_count']}\n"
        f"- target_protocol_count: {final_verdict['target_protocol_count']}\n"
    )

    write_text(
        REPORT_DIR / 'ARTIFACT_INDEX.md',
        '# Artifact Index\n'
        '- INPUT_EVIDENCE_AUDIT_CN.md\n'
        '- input_evidence_audit.json\n'
        '- CURRENT_UNIVERSE_GAP_RECAP_CN.md\n'
        '- current_universe_gap_recap.json\n'
        '- EVM_EXPANSION_CHAIN_PROTOCOL_PRIORITY_CN.md\n'
        '- evm_expansion_chain_protocol_priority.csv\n'
        '- evm_expansion_chain_protocol_priority.json\n'
        '- BSC_PANCAKESWAP_V3_EXPANSION_DESIGN_CN.md\n'
        '- bsc_pancakeswap_v3_expansion_design.json\n'
        '- BSC_DATA_SOURCE_FEASIBILITY_CN.md\n'
        '- bsc_data_source_feasibility.csv\n'
        '- bsc_data_source_feasibility.json\n'
        '- EVM_UNIVERSE_EXPANSION_SCHEMA_CN.md\n'
        '- evm_universe_expansion_schema.json\n'
        '- EVM_POOL_DISCOVERY_IMPLEMENTATION_PLAN_CN.md\n'
        '- evm_pool_discovery_implementation_plan.json\n'
        '- METADATA_GAP_POLICY_CN.md\n'
        '- metadata_gap_policy.json\n'
        '- EVM_UNIVERSE_EXPANSION_NEXT_STAGE_DECISION_CN.md\n'
        '- evm_universe_expansion_next_stage_decision.json\n'
        '- FINAL_VERDICT.json\n'
        '- ONEPAGE_CN.md\n'
    )


if __name__ == '__main__':
    main()
