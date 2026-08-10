#!/usr/bin/env python3
"""Machine-check the C6 prerequisites without signing or broadcasting.

The checker is intentionally evidence-oriented: absence of deployment-only
evidence is FAIL, not an optimistic PASS.  SQLite is opened read-only,
keystore/password files are stat'ed but never read, and the only network calls
are ``eth_chainId``/``eth_blockNumber`` against the repository's free public
RPC pool.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.base_m1_executor_v1 import (
    Action,
    ExecutionPolicy,
    ExecutionState,
    IntentValidator,
    Ledger,
    LiveTradingLocked,
    LiveUnlock,
    PolicyRejected,
    Protocol,
    UNISWAP_V3_NPM,
    Broadcaster,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool


DEFAULT_SCANNER_DB = ROOT / "reports/lp_scanner/scanner.db"
DEFAULT_C3 = ROOT / "reports/lp_defensive_exit_lower_replay/20260809_c3_acceptance/results.json"
DEFAULT_SYSTEMD = ROOT / "deploy/systemd/lpbot-base-m1-executor.service.example"
BASE_CHAIN_ID = 8453


@dataclass(frozen=True)
class Check:
    check_id: str
    label: str
    passed: bool
    detail: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ro_connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def check_candidate(db_path: Path) -> Check:
    try:
        with _ro_connect(db_path) as connection:
            latest_row = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()
            latest = latest_row[0] if latest_row else None
            accepted = 0 if latest is None else int(connection.execute(
                "SELECT count(*) FROM opportunity_scores WHERE as_of=? AND accepted=1", (latest,)
            ).fetchone()[0])
        return Check(
            "candidate", "存在 ≥1 个全闸通过候选", accepted >= 1,
            f"latest={latest}; accepted={accepted}",
            {"scanner_db": str(db_path), "as_of": latest, "accepted": accepted},
        )
    except (OSError, sqlite3.Error) as exc:
        return Check("candidate", "存在 ≥1 个全闸通过候选", False, f"证据不可读：{type(exc).__name__}", {"scanner_db": str(db_path)})


class _NoSendRpc:
    def __init__(self):
        self.send_calls = 0

    def broadcast_raw(self, _raw: str) -> str:
        self.send_calls += 1
        raise AssertionError("broadcast transport must remain unreachable")


def check_broadcast_lock(environ: Mapping[str, str], systemd_path: Path) -> Check:
    unlock = LiveUnlock.from_process_start("", environ)
    rpc = _NoSendRpc()
    broadcaster = Broadcaster(rpc, unlock)
    blocked = False
    try:
        broadcaster.broadcast("0xunsigned-placeholder")
    except LiveTradingLocked:
        blocked = True
    unit_text = systemd_path.read_text(encoding="utf-8") if systemd_path.exists() else ""
    unit_default_false = "Environment=LIVE_TRADING=false" in unit_text
    passed = (
        blocked
        and rpc.send_calls == 0
        and not unlock.environment_enabled
        and not unlock.startup_confirmed
        and not unlock.unlocked
        and unit_default_false
    )
    return Check(
        "broadcast_lock", "C4 广播锁 false 且未解锁", passed,
        f"runtime_locked={blocked}; LIVE_TRADING_true={unlock.environment_enabled}; startup_confirmed={unlock.startup_confirmed}; unit_default_false={unit_default_false}; send_calls={rpc.send_calls}",
        {
            "runtime_locked": blocked,
            "live_trading_true": unlock.environment_enabled,
            "startup_confirmed": unlock.startup_confirmed,
            "systemd_default_false": unit_default_false,
            "transport_send_calls": rpc.send_calls,
        },
    )


def _safe_file_stat(path: Path, expected_uid: int | None) -> tuple[bool, dict[str, Any]]:
    try:
        info = path.stat()
    except OSError as exc:
        return False, {"path": str(path), "error": type(exc).__name__}
    mode = stat.S_IMODE(info.st_mode)
    regular = stat.S_ISREG(info.st_mode)
    owner_ok = expected_uid is None or info.st_uid == expected_uid
    return regular and mode & 0o077 == 0 and owner_ok, {
        "path": str(path), "regular": regular, "mode": oct(mode),
        "uid": info.st_uid, "expected_uid": expected_uid, "owner_ok": owner_ok,
        "contents_read": False,
    }


def check_keystore_isolation(
    keystore: Path | None,
    password_file: Path | None,
    executor_uid: int | None,
    strategy_uid: int | None,
) -> Check:
    if keystore is None or password_file is None or executor_uid is None or strategy_uid is None:
        return Check(
            "keystore_isolation", "keystore 权限与进程隔离", False,
            "未配置 keystore/password/executor_uid/strategy_uid；未读取任何密钥内容",
            {"configured": False, "contents_read": False},
        )
    key_ok, key_evidence = _safe_file_stat(keystore, executor_uid)
    password_ok, password_evidence = _safe_file_stat(password_file, executor_uid)
    distinct_users = executor_uid != strategy_uid
    passed = key_ok and password_ok and distinct_users
    return Check(
        "keystore_isolation", "keystore 权限与进程隔离", passed,
        f"keystore={key_ok}; password={password_ok}; distinct_users={distinct_users}; contents_read=false",
        {"configured": True, "keystore": key_evidence, "password": password_evidence, "distinct_users": distinct_users},
    )


def check_exit_only() -> Check:
    wallet = "0x1111111111111111111111111111111111111111"
    pool = "0x2222222222222222222222222222222222222222"
    token = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    now = 1_800_000_000
    with tempfile.TemporaryDirectory(prefix="lp-c6-preflight-") as directory:
        ledger = Ledger(Path(directory) / "ledger.jsonl")
        policy = ExecutionPolicy(allowed_pools=frozenset({pool}))
        validator = IntentValidator(policy, ledger, now=lambda: now)
        common = dict(
            protocol=Protocol.UNISWAP_V3, npm=UNISWAP_V3_NPM, wallet=wallet,
            pool=pool, strategy_decision_id="preflight", risk_verdict_id="preflight",
            notional_usd=0.0, slippage_bps=0, deadline=now + 60, token=token,
            spender=UNISWAP_V3_NPM,
        )
        from execution.base_m1_executor_v1 import Intent
        mint_blocked = False
        try:
            validator.validate(Intent(action=Action.MINT, idempotency_key="mint", token0=token, token1=token, **common), ExecutionState.EXIT_ONLY)
        except PolicyRejected as exc:
            mint_blocked = "EXIT_ONLY" in str(exc)
        revoke_allowed = True
        try:
            validator.validate(Intent(action=Action.REVOKE, idempotency_key="revoke", **common), ExecutionState.EXIT_ONLY)
        except Exception:
            revoke_allowed = False
    return Check(
        "kill_exit_only", "kill switch 与 EXIT_ONLY 通路", mint_blocked and revoke_allowed,
        f"mint_blocked={mint_blocked}; revoke_allowed={revoke_allowed}",
        {"mint_blocked": mint_blocked, "revoke_allowed": revoke_allowed, "network_calls": 0},
    )


def check_c3(path: Path) -> Check:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        scenarios = payload.get("scenarios") or payload.get("results") or []
        verdict = str(payload.get("verdict") or payload.get("result") or "").upper()
        all_pass = bool(scenarios) and all(
            row.get("passed") is True
            or str(row.get("result") or row.get("verdict") or "").upper() == "PASS"
            for row in scenarios
        )
        passed = payload.get("passed") is True or verdict == "PASS" or all_pass
        return Check(
            "c3_lower_exit", "下破退出演练 C3", passed,
            f"verdict={verdict or 'derived'}; scenarios={len(scenarios)}; all_pass={all_pass}",
            {"artifact": str(path), "verdict": verdict, "scenarios": len(scenarios), "all_pass": all_pass},
        )
    except (OSError, ValueError, TypeError) as exc:
        return Check("c3_lower_exit", "下破退出演练 C3", False, f"证据不可读：{type(exc).__name__}", {"artifact": str(path)})


def check_reconciliation(root: Path = ROOT) -> Check:
    cli = root / "cmd/lpbot-recon/main.go"
    live_impl = root / "cmd/lpbot/base_tx_reconcile_live.go"
    cli_text = cli.read_text(encoding="utf-8") if cli.exists() else ""
    live_exists = live_impl.exists()
    cli_is_stub = "Phase 3 stub" in cli_text
    passed = live_exists and not cli_is_stub
    return Check(
        "ledger_reconciliation", "账本对账工具可用", passed,
        f"base_live_impl={live_exists}; operator_cli_stub={cli_is_stub}",
        {"live_implementation": str(live_impl), "operator_cli": str(cli), "operator_cli_stub": cli_is_stub},
    )


def _unresolved_rpc_incidents(db_path: Path) -> int | None:
    try:
        with _ro_connect(db_path) as connection:
            exists = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='rpc_severe_incidents'"
            ).fetchone()[0]
            if not exists:
                return None
            return int(connection.execute(
                "SELECT count(*) FROM rpc_severe_incidents WHERE resolved_at IS NULL"
            ).fetchone()[0])
    except (OSError, sqlite3.Error):
        return None


def default_rpc_probe() -> dict[str, Any]:
    pool = RpcPool("base")
    chain_id = int(pool.call("eth_chainId", []), 16)
    block = int(pool.call("eth_blockNumber", []), 16)
    return {"chain_id": chain_id, "block_number": block, **pool.health_snapshot()}


def check_rpc(db_path: Path, probe: Callable[[], Mapping[str, Any]]) -> Check:
    unresolved = _unresolved_rpc_incidents(db_path)
    try:
        evidence = dict(probe())
        state = str(evidence.get("state") or "UNKNOWN").upper()
        chain_ok = int(evidence.get("chain_id") or 0) == BASE_CHAIN_ID
        block_ok = int(evidence.get("block_number") or 0) > 0
        state_ok = state not in {"EXIT_ONLY", "KILLED", "UNKNOWN"}
        incidents_ok = unresolved == 0
        passed = chain_ok and block_ok and state_ok and incidents_ok
        evidence["unresolved_severe_incidents"] = unresolved
        return Check(
            "free_rpc", "免费 RPC 健康且无 EXIT_ONLY/KILLED", passed,
            f"chain_id={evidence.get('chain_id')}; block={evidence.get('block_number')}; state={state}; unresolved={unresolved}",
            evidence,
        )
    except Exception as exc:
        return Check(
            "free_rpc", "免费 RPC 健康且无 EXIT_ONLY/KILLED", False,
            f"只读探针失败：{type(exc).__name__}",
            {"unresolved_severe_incidents": unresolved, "error_type": type(exc).__name__},
        )


def check_wallet_balance(wallet: str | None, balance_probe: Callable[[str], Mapping[str, Any]] | None) -> Check:
    if wallet is None or balance_probe is None:
        return Check(
            "wallet_gas", "钱包余额与 gas 储备（若配置）", False,
            "未配置钱包/余额探针；未访问钱包、未读取 keystore",
            {"configured": False, "wallet_access": 0, "keystore_reads": 0},
        )
    try:
        evidence = dict(balance_probe(wallet))
        passed = bool(evidence.get("balance_ok")) and bool(evidence.get("gas_reserve_ok"))
        return Check("wallet_gas", "钱包余额与 gas 储备（若配置）", passed, f"balance_ok={evidence.get('balance_ok')}; gas_reserve_ok={evidence.get('gas_reserve_ok')}", evidence)
    except Exception as exc:
        return Check("wallet_gas", "钱包余额与 gas 储备（若配置）", False, f"余额探针失败：{type(exc).__name__}", {"error_type": type(exc).__name__})


def evaluate(
    *,
    scanner_db: Path = DEFAULT_SCANNER_DB,
    c3_path: Path = DEFAULT_C3,
    systemd_path: Path = DEFAULT_SYSTEMD,
    environ: Mapping[str, str] | None = None,
    keystore: Path | None = None,
    password_file: Path | None = None,
    executor_uid: int | None = None,
    strategy_uid: int | None = None,
    wallet: str | None = None,
    rpc_probe: Callable[[], Mapping[str, Any]] = default_rpc_probe,
    balance_probe: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    checks = [
        check_candidate(scanner_db),
        check_broadcast_lock(os.environ if environ is None else environ, systemd_path),
        check_keystore_isolation(keystore, password_file, executor_uid, strategy_uid),
        check_exit_only(),
        check_c3(c3_path),
        check_reconciliation(ROOT),
        check_rpc(scanner_db, rpc_probe),
        check_wallet_balance(wallet, balance_probe),
    ]
    return {
        "schema": "lp_c6_preflight_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if all(check.passed for check in checks) else "FAIL",
        "passed": sum(check.passed for check in checks),
        "failed": sum(not check.passed for check in checks),
        "checks": [check.to_dict() for check in checks],
        "safety": {"signed": False, "broadcast_count": 0, "wallet_access": 0 if wallet is None else "read_only_balance_probe"},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# C6 preflight（只读）",
        "",
        f"结论：**{report['overall']}**；PASS {report['passed']} / FAIL {report['failed']}。",
        "",
        "| 条件 | 结果 | 证据摘要 |",
        "|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(f"| {check['label']} | {'PASS' if check['passed'] else 'FAIL'} | {check['detail']} |")
    lines.extend([
        "",
        "缺失证据按 FAIL 处理。脚本不读取 keystore 内容；本次 signed=false、broadcast_count=0。",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C6 machine-readable read-only preflight")
    parser.add_argument("--scanner-db", type=Path, default=DEFAULT_SCANNER_DB)
    parser.add_argument("--c3", type=Path, default=DEFAULT_C3)
    parser.add_argument("--systemd", type=Path, default=DEFAULT_SYSTEMD)
    parser.add_argument("--keystore", type=Path)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--executor-uid", type=int)
    parser.add_argument("--strategy-uid", type=int)
    parser.add_argument("--wallet")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = evaluate(
        scanner_db=args.scanner_db, c3_path=args.c3, systemd_path=args.systemd,
        keystore=args.keystore, password_file=args.password_file,
        executor_uid=args.executor_uid, strategy_uid=args.strategy_uid,
        wallet=args.wallet,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "preflight.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"C6 preflight {report['overall']}: PASS={report['passed']} FAIL={report['failed']}")
    # A FAIL is the expected machine verdict, not a tool execution error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
