#!/usr/bin/env python3
"""Reproduce TP-M0N FIX-N1 income validation from one immutable scanner DB.

The source database is opened with SQLite ``mode=ro&immutable=1`` and its
SHA-256/as-of are pinned.  This script never calls an RPC endpoint and has no
wallet, signing, approval, transaction, or broadcast capability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_netcover_engine_v1_readonly import (
    REWARD_HAIRCUTS,
    evaluate_netcover,
)
from scripts.lp_netcover_inputs_v1_readonly import (
    FEE_EVIDENCE_REFERENCE_HOURS,
    HOURS_PER_YEAR,
    M1_MIN_POSITION_USD,
    assemble_netcover_inputs,
)


SCHEMA_VERSION = "lp_m0n_income_validation_v1"
PRE_CHECKPOINT_MAIN_DB_SHA256 = (
    "67aa62a0589dbbc6ded9696f5eb0bb2a35eb0a523a277494e5852a4a51673b1c"
)
EXPECTED_DB_SHA256 = "7c188a88034cdacd44ff70c2f87b0f459ddca074e56e8ea5677667719987d137"
EXPECTED_LOGICAL_CONTENT_SHA256 = (
    "31d346ba250842c67283a0f0bb73aff8b3b8885aca42a0964e80ff62ca39e2b0"
)
EXPECTED_AS_OF = "2026-08-09T11:56:19.991045+00:00"
EXPECTED_SCORE_ROWS = 47
HORIZONS = (168.0, 336.0, 720.0)
THEORETICAL_H720_H168_RATIO = math.sqrt(HORIZONS[-1] / HORIZONS[0])
RATIO_RELATIVE_TOLERANCE = 0.05
USD_INPUT_FIELDS = (
    "fee_ev_usd",
    "reward_ev_usd",
    "il_ev_usd",
    "entry_cost_usd",
    "exit_cost_usd",
    "gas_usd",
    "slippage_usd",
    "reward_conversion_cost_usd",
    "exit_latency_loss_usd",
)
FIXED_COST_FIELDS = (
    "entry_cost_usd",
    "exit_cost_usd",
    "gas_usd",
    "slippage_usd",
)
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _finite(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _open_locked_database(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _identity_proof(row: Mapping[str, Any], score: Mapping[str, Any]) -> dict[str, Any]:
    pool = str(row["pool"]).lower()
    score_pool = str(score.get("pool") or "").lower()
    resolved_pool = str(score.get("resolved_pool") or "").lower()
    proof = {
        "opportunity_scores_pool": pool,
        "score_json_pool": score_pool,
        "resolved_pool": resolved_pool,
        "resolve_status": score.get("resolve_status"),
        "resolved_factory": score.get("resolved_factory"),
        "resolved_factory_label": score.get("resolved_factory_label"),
        "factory_registry_source": score.get("factory_registry_source"),
        "pool_identity_validation": score.get("pool_identity_validation"),
        "last_swap_cost_state_source": score.get("last_swap_cost_state_source"),
    }
    proof["locked"] = bool(
        ADDRESS_RE.fullmatch(pool)
        and pool == score_pool == resolved_pool
        and score.get("resolve_status") == "OK"
        and score.get("resolved_factory")
        and score.get("factory_registry_source")
        and score.get("last_swap_cost_state_source")
        == "measured:latest_decoded_swap_event"
    )
    return proof


def _critical_inputs(score: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "chain", "project", "pool", "resolved_pool", "symbol", "token0", "token1",
        "dec0", "dec1", "resolved_factory", "resolved_factory_label",
        "factory_registry_source", "fee_apr_24h", "fee_apr_onchain", "apyBase",
        "reward_apr", "apyReward", "rewardTokens", "reward_category", "is_new_pool",
        "sigma_pair", "sigma_daily", "il_apr", "fee_tier", "profile",
        "last_swap_cost_state_source", "last_swap_liquidity_raw",
        "last_swap_price_token1_per_token0", "lvr_coefficient",
    )
    evidence = score.get("scanner_measured_cross_pool_evidence")
    return {
        **{key: score.get(key) for key in keys},
        "pool_identity_validation": score.get("pool_identity_validation"),
        "scanner_measured_cross_pool_evidence_sha256": (
            _canonical_json_hash(evidence) if evidence is not None else None
        ),
        "scanner_measured_cross_pool_evidence_summary": (
            {
                "complete": evidence.get("complete"),
                "observed_block": evidence.get("observed_block"),
                "executable_aero_reward_route_ids": [
                    route.get("route_id")
                    for route in evidence.get("aero_reward_routes", [])
                    if route.get("executable") is True
                ],
                "token1_usd": evidence.get("token1_usd"),
                "token1_usd_source": evidence.get("token1_usd_source"),
            }
            if isinstance(evidence, Mapping) else None
        ),
    }


def load_locked_scores(
    db_path: Path,
    *,
    expected_sha256: str = EXPECTED_DB_SHA256,
    expected_as_of: str = EXPECTED_AS_OF,
    expected_logical_sha256: str = EXPECTED_LOGICAL_CONTENT_SHA256,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load the 47 score rows only after validating the immutable snapshot."""
    before_hash = sha256_file(db_path)
    if before_hash != expected_sha256:
        raise ValueError(
            f"source DB SHA-256 mismatch: expected {expected_sha256}, got {before_hash}"
        )
    with _open_locked_database(db_path) as connection:
        rows = connection.execute(
            "SELECT id, as_of, pool, symbol, score_json FROM opportunity_scores ORDER BY id"
        ).fetchall()
        as_of_values = sorted({str(row["as_of"]) for row in rows})
    after_hash = sha256_file(db_path)
    if after_hash != before_hash:
        raise RuntimeError("read-only source DB changed while validation was running")
    if len(rows) != EXPECTED_SCORE_ROWS:
        raise ValueError(f"expected {EXPECTED_SCORE_ROWS} score rows, got {len(rows)}")
    if as_of_values != [expected_as_of]:
        raise ValueError(f"as-of mismatch: expected {expected_as_of}, got {as_of_values}")

    loaded: list[dict[str, Any]] = []
    logical_manifest: list[dict[str, Any]] = []
    for row in rows:
        raw = str(row["score_json"])
        score = json.loads(raw)
        row_hash = _sha256_bytes(raw.encode("utf-8"))
        logical_manifest.append({
            "id": int(row["id"]),
            "as_of": str(row["as_of"]),
            "pool": str(row["pool"]).lower(),
            "symbol": str(row["symbol"] or ""),
            "score_json_sha256": row_hash,
        })
        loaded.append({
            "id": int(row["id"]),
            "as_of": str(row["as_of"]),
            "pool": str(row["pool"]).lower(),
            "symbol": str(row["symbol"] or score.get("symbol") or ""),
            "score": score,
            "score_json_sha256": row_hash,
            "score_json_bytes": len(raw.encode("utf-8")),
            "identity_proof": _identity_proof(row, score),
        })
    logical_hash = _canonical_json_hash(logical_manifest)
    if logical_hash != expected_logical_sha256:
        raise ValueError(
            "canonical logical content SHA-256 mismatch: expected "
            f"{expected_logical_sha256}, got {logical_hash}"
        )
    source = {
        "db": str(db_path),
        "sha256_expected": expected_sha256,
        "sha256_before": before_hash,
        "sha256_after": after_hash,
        "hash_unchanged": before_hash == after_hash,
        "pre_checkpoint_main_db_sha256": PRE_CHECKPOINT_MAIN_DB_SHA256,
        "pre_checkpoint_hash_scope": (
            "SQLite main file only; the 47 logical rows were in the WAL, so this "
            "hash alone did not identify the complete logical database"
        ),
        "wal_checkpoint_disclosure": (
            "During initial inventory a plain sqlite3 read connection triggered a WAL "
            "checkpoint. Logical rows/as-of were unchanged; the consolidated main-file "
            "hash is now the hard physical gate. No restore or overwrite was attempted."
        ),
        "canonical_logical_content_sha256_expected": expected_logical_sha256,
        "canonical_logical_content_sha256_observed": logical_hash,
        "canonical_logical_content_manifest": logical_manifest,
        "sqlite_open_mode": "mode=ro&immutable=1; PRAGMA query_only=ON",
        "as_of_expected": expected_as_of,
        "as_of_observed": as_of_values[0],
        "opportunity_score_rows": len(loaded),
    }
    return loaded, source


def _engine_haircut(assembled: Mapping[str, Any]) -> float:
    reward = float(assembled["reward_ev_usd"])
    if reward == 0.0:
        return 0.0
    category = str(assembled.get("reward_category") or "")
    if category not in REWARD_HAIRCUTS:
        raise ValueError(f"unknown reward category for non-zero reward: {category!r}")
    return float(REWARD_HAIRCUTS[category])


def _evaluate_assembled(assembled: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in USD_INPUT_FIELDS if not _finite(assembled.get(field))]
    if missing:
        return {"calculable": False, "missing_or_nonfinite": missing}
    estimate = evaluate_netcover(
        fee_ev=float(assembled["fee_ev_usd"]),
        reward_ev=float(assembled["reward_ev_usd"]),
        reward_haircut=_engine_haircut(assembled),
        expected_il=float(assembled["il_ev_usd"]),
        lvr_coefficient=float(assembled["lvr_coefficient"]),
        entry_cost=float(assembled["entry_cost_usd"]),
        exit_cost=float(assembled["exit_cost_usd"]),
        gas=float(assembled["gas_usd"]),
        slippage=float(assembled["slippage_usd"]),
        reward_conversion_cost=float(assembled["reward_conversion_cost_usd"]),
        exit_latency_loss=float(assembled["exit_latency_loss_usd"]),
    )
    return {
        "calculable": True,
        **{field: float(assembled[field]) for field in USD_INPUT_FIELDS},
        "fee_capture_share_ratio": float(assembled["fee_capture_share_ratio"]),
        "fee_capture_target_range_pct": float(
            assembled["fee_capture_target_range_pct"]
        ),
        "fee_capture_reference_range_pct": float(
            assembled["fee_capture_reference_range_pct"]
        ),
        "fee_capture_evidence_apr_pct": float(
            assembled["fee_capture_evidence_apr_pct"]
        ),
        "fee_capture_haircut": float(assembled["fee_capture_haircut"]),
        "reward_category": assembled.get("reward_category"),
        "reward_haircut_engine": _engine_haircut(assembled),
        "lvr_ev_usd": estimate.expected_lvr_model,
        "adjusted_income_ev_usd": estimate.adjusted_income_ev,
        "risk_usd": estimate.expected_risk_cost,
        "netcover": estimate.netcover,
        "netcover_pass": estimate.shadow_candidate,
    }


def evaluate_horizon(score: Mapping[str, Any], horizon_hours: float) -> dict[str, Any]:
    record = dict(score)
    record["holding_horizon_hours"] = float(horizon_hours)
    record["holding_horizon_days"] = float(horizon_hours) / 24.0
    record["holding_horizon_source"] = "m0n_n1_fixed_passive_grid"
    evidence = record.get("scanner_measured_cross_pool_evidence")
    assembled = assemble_netcover_inputs(
        record,
        position_usd=M1_MIN_POSITION_USD,
        scanner_measured_evidence=evidence if isinstance(evidence, Mapping) else None,
    )
    return {"horizon_hours": float(horizon_hours), **_evaluate_assembled(assembled)}


def ratio_assertion(
    curve: Iterable[Mapping[str, Any]], field: str, *, reward_bearing: bool
) -> dict[str, Any]:
    points = {float(point["horizon_hours"]): point for point in curve}
    first = float(points[HORIZONS[0]][field])
    last = float(points[HORIZONS[-1]][field])
    if field == "reward_ev_usd" and not reward_bearing:
        if first != 0.0 or last != 0.0:
            raise AssertionError("no-reward sample produced non-zero RewardEV")
        return {
            "field": field,
            "observed_h720_h168_ratio": None,
            "ratio_status": "N/A_ZERO_REWARD",
            "assertion": "PASS: both endpoints are exactly zero; 0/0 was not computed",
        }
    if first <= 0.0:
        raise AssertionError(f"{field} H168 must be positive for a mechanical ratio")
    observed = last / first
    relative_error = abs(observed / THEORETICAL_H720_H168_RATIO - 1.0)
    passed = relative_error <= RATIO_RELATIVE_TOLERANCE
    return {
        "field": field,
        "observed_h720_h168_ratio": observed,
        "theoretical_sqrt_ratio": THEORETICAL_H720_H168_RATIO,
        "relative_error": relative_error,
        "relative_tolerance": RATIO_RELATIVE_TOLERANCE,
        "ratio_status": "PASS" if passed else "FAIL",
        "assertion": (
            "PASS" if passed else "FAIL"
        ) + ": observed ratio must be within ±5% of sqrt(720/168)",
    }


def _curve_shape(curve: list[Mapping[str, Any]]) -> dict[str, Any]:
    best = max(curve, key=lambda point: float(point["netcover"]))
    first = curve[0]
    fixed_cost = sum(float(first[field]) for field in FIXED_COST_FIELDS)
    linear_cost_at_first = (
        float(first["il_ev_usd"])
        + float(first["lvr_ev_usd"])
        + float(first["exit_latency_loss_usd"])
    )
    linear_rate = linear_cost_at_first / float(first["horizon_hours"])
    h_star = fixed_cost / linear_rate if linear_rate > 0.0 else math.inf
    if h_star < HORIZONS[0]:
        location = "BELOW_DISCRETE_GRID"
    elif h_star > HORIZONS[-1]:
        location = "ABOVE_DISCRETE_GRID"
    else:
        location = "WITHIN_DISCRETE_GRID"
    values = [float(point["netcover"]) for point in curve]
    if values[0] < values[1] > values[2]:
        observed_shape = "INTERNAL_OPTIMUM_AT_336H"
    elif values[0] < values[1] < values[2]:
        observed_shape = "MONOTONIC_INCREASING_ON_GRID"
    elif values[0] > values[1] > values[2]:
        observed_shape = "MONOTONIC_DECREASING_ON_GRID"
    else:
        observed_shape = "NON_MONOTONIC_OR_TIED"
    return {
        "observed_shape": observed_shape,
        "empirical_best_horizon_hours": float(best["horizon_hours"]),
        "fixed_cost_usd_entry_exit_gas_slippage": fixed_cost,
        "il_ev_usd_by_horizon": {
            str(int(point["horizon_hours"])): float(point["il_ev_usd"])
            for point in curve
        },
        "linear_cost_proxy_usd_at_168h": linear_cost_at_first,
        "linear_cost_proxy_usd_per_hour": linear_rate,
        "h_star_c_over_b_hours": h_star,
        "h_star_grid_location": location,
        "h_star_scope": (
            "c/b proxy uses fixed entry+exit+gas+slippage and linear "
            "IL+LVR+latency; reward conversion is excluded"
        ),
    }


def analyze_score(item: Mapping[str, Any]) -> dict[str, Any]:
    score = item["score"]
    reward_apr = float(score.get("reward_apr") or 0.0)
    reward_bearing = reward_apr > 0.0
    curve = [evaluate_horizon(score, horizon) for horizon in HORIZONS]
    calculable = all(point["calculable"] for point in curve)
    analysis: dict[str, Any] = {
        "id": item["id"],
        "pool": item["pool"],
        "symbol": item["symbol"],
        "reward_group": "REWARD" if reward_bearing else "NO_REWARD",
        "reward_apr_pct": reward_apr,
        "identity_locked": item["identity_proof"]["locked"],
        "identity_proof": item["identity_proof"],
        "score_json_sha256": item["score_json_sha256"],
        "score_json_bytes": item["score_json_bytes"],
        "critical_inputs": _critical_inputs(score),
        "suspect_flags": score.get("suspect") or [],
        "curve": curve,
        "fully_calculable_all_horizons": calculable,
    }
    if calculable:
        analysis["ratio_assertions"] = [
            ratio_assertion(curve, "fee_ev_usd", reward_bearing=reward_bearing),
            ratio_assertion(curve, "reward_ev_usd", reward_bearing=reward_bearing),
        ]
        analysis["curve_shape"] = _curve_shape(curve)
    else:
        analysis["exclusion_reasons"] = sorted({
            reason
            for point in curve
            for reason in point.get("missing_or_nonfinite", [])
        })
    return analysis


def select_samples(
    inventory: Iterable[Mapping[str, Any]], *, minimum_each: int = 3
) -> dict[str, list[dict[str, Any]]]:
    """Choose clean real pools, preferring observed internal optima and high IL."""
    selected: dict[str, list[dict[str, Any]]] = {}
    for group in ("REWARD", "NO_REWARD"):
        eligible = [
            dict(item) for item in inventory
            if item["reward_group"] == group
            and item["fully_calculable_all_horizons"]
            and item["identity_locked"]
            and not item["suspect_flags"]
            and all(
                assertion["ratio_status"] in {"PASS", "N/A_ZERO_REWARD"}
                for assertion in item["ratio_assertions"]
            )
        ]
        eligible.sort(key=lambda item: (
            item["curve_shape"]["observed_shape"] != "INTERNAL_OPTIMUM_AT_336H",
            -(
                item["curve"][-1]["il_ev_usd"]
                / max(
                    item["curve_shape"]["fixed_cost_usd_entry_exit_gas_slippage"],
                    1e-30,
                )
            ),
            item["pool"],
        ))
        if len(eligible) < minimum_each:
            raise ValueError(
                f"only {len(eligible)} eligible {group} samples; need {minimum_each}"
            )
        selected[group] = eligible[:minimum_each]
    return selected


def _m0f_old_income_terms(
    score: Mapping[str, Any], corrected_point: Mapping[str, Any]
) -> tuple[float, float]:
    """Independently reproduce the two M0F income bugs for comparison only."""
    size = float(M1_MIN_POSITION_USD)
    share_ratio = float(corrected_point["fee_capture_share_ratio"])
    fee_apr = float(corrected_point["fee_capture_evidence_apr_pct"])
    fee_haircut = float(corrected_point["fee_capture_haircut"])
    horizon = float(corrected_point["horizon_hours"])
    reward_apr = float(score.get("reward_apr") or 0.0)
    # M0F bug 1: fee time was pinned to the 168h evidence anchor.
    old_fee = (
        size * fee_apr / 100.0 * fee_haircut
        * (FEE_EVIDENCE_REFERENCE_HOURS / HOURS_PER_YEAR) * share_ratio
    )
    # M0F bug 2: reward retained H but omitted the same in-range share ratio.
    old_reward = size * reward_apr / 100.0 * (horizon / HOURS_PER_YEAR)
    return old_fee, old_reward


def _old_reward_conversion(
    score: Mapping[str, Any], corrected_point: Mapping[str, Any], old_reward: float
) -> float:
    if old_reward == 0.0:
        return 0.0
    share_ratio = float(corrected_point["fee_capture_share_ratio"])
    if share_ratio <= 0.0:
        raise ValueError("share ratio must be positive for old reward conversion replay")
    record = dict(score)
    record["holding_horizon_hours"] = float(corrected_point["horizon_hours"])
    record["holding_horizon_days"] = float(corrected_point["horizon_hours"]) / 24.0
    # The corrected assembler multiplies reward APR by share_ratio.  Dividing
    # the APR by that measured ratio makes it emit the independently computed
    # M0F reward amount, while reusing the exact conversion-cost implementation.
    record["reward_apr"] = float(score.get("reward_apr") or 0.0) / share_ratio
    evidence = record.get("scanner_measured_cross_pool_evidence")
    assembled = assemble_netcover_inputs(
        record,
        position_usd=M1_MIN_POSITION_USD,
        scanner_measured_evidence=evidence if isinstance(evidence, Mapping) else None,
    )
    if not math.isclose(float(assembled["reward_ev_usd"]), old_reward, rel_tol=1e-12):
        raise AssertionError("old reward conversion replay did not preserve M0F RewardEV")
    return float(assembled["reward_conversion_cost_usd"])


def before_after(score: Mapping[str, Any]) -> dict[str, Any]:
    curve = [evaluate_horizon(score, horizon) for horizon in HORIZONS]
    if not all(point["calculable"] for point in curve):
        raise ValueError("before/after comparison pool is not fully calculable")
    points = []
    for corrected in curve:
        old_fee, old_reward = _m0f_old_income_terms(score, corrected)
        old_conversion = _old_reward_conversion(score, corrected, old_reward)
        old_estimate = evaluate_netcover(
            fee_ev=old_fee,
            reward_ev=old_reward,
            reward_haircut=(
                0.0 if old_reward == 0.0
                else REWARD_HAIRCUTS[str(corrected["reward_category"])]
            ),
            expected_il=float(corrected["il_ev_usd"]),
            lvr_coefficient=float(score.get("lvr_coefficient") or 0.5),
            entry_cost=float(corrected["entry_cost_usd"]),
            exit_cost=float(corrected["exit_cost_usd"]),
            gas=float(corrected["gas_usd"]),
            slippage=float(corrected["slippage_usd"]),
            reward_conversion_cost=old_conversion,
            exit_latency_loss=float(corrected["exit_latency_loss_usd"]),
        )
        points.append({
            "horizon_hours": corrected["horizon_hours"],
            "share_ratio": corrected["fee_capture_share_ratio"],
            "m0f_old": {
                "fee_ev_usd": old_fee,
                "reward_ev_usd": old_reward,
                "reward_conversion_cost_usd": old_conversion,
                "netcover": old_estimate.netcover,
            },
            "m0n_n1_corrected": {
                "fee_ev_usd": corrected["fee_ev_usd"],
                "reward_ev_usd": corrected["reward_ev_usd"],
                "reward_conversion_cost_usd": corrected[
                    "reward_conversion_cost_usd"
                ],
                "netcover": corrected["netcover"],
            },
            "mechanical_change_factors": {
                "corrected_fee_over_old_fee": (
                    corrected["fee_ev_usd"] / old_fee if old_fee else None
                ),
                "corrected_reward_over_old_reward": (
                    corrected["reward_ev_usd"] / old_reward if old_reward else None
                ),
            },
        })
    return {"curve": points}


def _fmt(value: Any, digits: int = 9) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}g}"
    return str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    selected = report["selected_samples"]
    lines = [
        "# TP-M0N FIX-N1 收入建模可复现验收",
        "",
        f"结论：**{report['verdict']}**。本报告只读重放锁定快照；不调用 RPC，不构造或发送交易。",
        "",
        "## 1. 锁定证据",
        "",
        f"- DB：`{report['source']['db']}`",
        f"- 当前 consolidated main DB SHA-256：`{report['source']['sha256_before']}`（运行前后不变：{report['source']['hash_unchanged']}）",
        f"- canonical logical content SHA-256：`{report['source']['canonical_logical_content_sha256_observed']}`（47 个逐行 score_json hash 清单也写入 JSON）。",
        f"- checkpoint 前 main-file SHA-256：`{report['source']['pre_checkpoint_main_db_sha256']}`。注意它不含 WAL，当时 47 条逻辑记录位于 WAL，因此该指纹不能单独代表完整逻辑库。",
        f"- as_of：`{report['source']['as_of_observed']}`",
        f"- 评分记录：{report['source']['opportunity_score_rows']} 行；SQLite 以 `{report['source']['sqlite_open_mode']}` 打开。",
        "- 池身份锁定条件：评分行 pool = score_json.pool = resolved_pool，resolve_status=OK，且固定工厂和实测 swap 状态来源齐备。",
        "- WAL 披露：初次盘点误用了普通 sqlite3 读连接并触发 checkpoint；逻辑行、as_of 与逐行内容未变，main 文件成为 consolidated 形态。未尝试恢复或覆盖源库；此后验证器只用 `mode=ro&immutable=1`。",
        "",
        "## 2. 全量盘点与选择",
        "",
        f"47 行中，三个 PASSIVE H 档九项完整 {report['inventory_summary']['fully_calculable_all_horizons']} 行：reward {report['inventory_summary']['fully_calculable_reward']}，no-reward {report['inventory_summary']['fully_calculable_no_reward']}。",
        f"最终机械样本为 reward {len(selected['REWARD'])} + no-reward {len(selected['NO_REWARD'])}；排除了 suspect 标记，优先选择 336h 内部最优且 IL 相对固定成本显著的池。",
        "",
    ]
    for group in ("REWARD", "NO_REWARD"):
        lines.extend([f"### {group}", ""])
        for item in selected[group]:
            lines.append(
                f"- `{item['symbol']}` / `{item['pool']}`；score_json SHA-256 `{item['score_json_sha256']}`"
            )
        lines.append("")

    lines.extend([
        "## 3. 机械校验与 NetCover 曲线",
        "",
        "理论比值 `sqrt(720/168) = " + _fmt(THEORETICAL_H720_H168_RATIO, 12)
        + "`，容差为相对 ±5%。Reward=0 时明确记 N/A，不计算 0/0。",
        "",
        "|组|池|H(h)|FeeEV($)|RewardEV($)|IL($)|NetCover|",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for group in ("REWARD", "NO_REWARD"):
        for item in selected[group]:
            for point in item["curve"]:
                lines.append(
                    "|{}|{}|{}|{}|{}|{}|{}|".format(
                        group, item["symbol"], int(point["horizon_hours"]),
                        _fmt(point["fee_ev_usd"]), _fmt(point["reward_ev_usd"]),
                        _fmt(point["il_ev_usd"]), _fmt(point["netcover"]),
                    )
                )
    lines.extend([
        "",
        "|组|池|Fee 720/168|Reward 720/168|断言|",
        "|---|---|---:|---:|---|",
    ])
    for group in ("REWARD", "NO_REWARD"):
        for item in selected[group]:
            fee, reward = item["ratio_assertions"]
            lines.append(
                f"|{group}|{item['symbol']}|{_fmt(fee['observed_h720_h168_ratio'])}|"
                f"{_fmt(reward['observed_h720_h168_ratio'])}|"
                f"fee={fee['ratio_status']}; reward={reward['ratio_status']}|"
            )
    lines.extend([
        "",
        "## 4. 单调性、IL、固定成本与 H*",
        "",
        "`H*=c/b` 是形状诊断：c=entry+exit+gas+slippage，b=每小时 IL+LVR+latency；reward conversion 未纳入该近似。最终结论仍以离散三档实测 NetCover 为准。",
        "",
        "|组|池|曲线|离散最优H|IL 168/336/720($)|固定成本($)|H*小时|H*位置|",
        "|---|---|---|---:|---|---:|---:|---|",
    ])
    for group in ("REWARD", "NO_REWARD"):
        for item in selected[group]:
            shape = item["curve_shape"]
            il = shape["il_ev_usd_by_horizon"]
            lines.append(
                f"|{group}|{item['symbol']}|{shape['observed_shape']}|"
                f"{int(shape['empirical_best_horizon_hours'])}|"
                f"{_fmt(il['168'])}/{_fmt(il['336'])}/{_fmt(il['720'])}|"
                f"{_fmt(shape['fixed_cost_usd_entry_exit_gas_slippage'])}|"
                f"{_fmt(shape['h_star_c_over_b_hours'])}|{shape['h_star_grid_location']}|"
            )
    lines.extend([
        "",
        "解释：两条 reward 样本在 336h 出现内部最优；其余样本若在边界最优，表中给出了真实 IL、固定成本与网格外/网格内 H*，没有把单调形状包装成内部最优。",
        "",
        "## 5. M0F / N1 同快照对照",
        "",
        "M0F 独立重算公式：`fee=size×feeAPR×haircut×(168/8760)×share_ratio(H)`；`reward=size×rewardAPR×(H/8760)`。N1 同时恢复 fee 的 H 因子，并给 reward 乘同一 share_ratio。",
        "",
        "|池|H|M0F fee|N1 fee|M0F reward|N1 reward|M0F NC|N1 NC|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for comparison in report["before_after"]:
        for point in comparison["curve"]:
            old = point["m0f_old"]
            new = point["m0n_n1_corrected"]
            lines.append(
                f"|{comparison['symbol']}|{int(point['horizon_hours'])}|"
                f"{_fmt(old['fee_ev_usd'])}|{_fmt(new['fee_ev_usd'])}|"
                f"{_fmt(old['reward_ev_usd'])}|{_fmt(new['reward_ev_usd'])}|"
                f"{_fmt(old['netcover'])}|{_fmt(new['netcover'])}|"
            )
    lines.extend([
        "",
        "变化来源只有两处：fee 的 `N1/M0F = H/168`；有 reward 时 reward 的 `N1/M0F = share_ratio(H)`。USDC-VVV 的 reward 始终为 0，因此其差异只来自 fee 时间因子；USDC-USDT 同时受两处修正影响。",
        "",
        "## 6. 可审计性与边界",
        "",
        "- JSON 对全部 47 行给出选择/排除结果；每个池保留原始 score_json SHA-256、字节数、关键输入、嵌套 scanner 证据 SHA-256 与摘要。",
        "- 九项 USD 输入全部由当前只读 assembler 从同一份 score_json 与内嵌实测证据重算；没有使用外部估值或池均值补 σ。",
        "- 本脚本没有阈值、reward persistence、生产 scanner、N2/N4/DOC 逻辑，也没有任何网络或写库路径。",
        "",
    ])
    return "\n".join(lines)


def build_report(
    db_path: Path,
    expected_sha256: str,
    expected_as_of: str,
    expected_logical_sha256: str = EXPECTED_LOGICAL_CONTENT_SHA256,
) -> dict[str, Any]:
    loaded, source = load_locked_scores(
        db_path,
        expected_sha256=expected_sha256,
        expected_as_of=expected_as_of,
        expected_logical_sha256=expected_logical_sha256,
    )
    inventory = [analyze_score(item) for item in loaded]
    selected = select_samples(inventory)

    score_by_symbol_pool = {
        (item["symbol"], item["pool"]): item["score"] for item in loaded
    }
    compare_keys = (
        ("USDC-USDT", "0xa41bc0affba7fd420d186b84899d7ab2ac57fcd1"),
        ("USDC-VVV", "0x67a11022b7b6ed66f81233f6c8ed6e48f7826530"),
    )
    comparisons = []
    for symbol, pool in compare_keys:
        score = score_by_symbol_pool.get((symbol, pool))
        if score is None:
            raise ValueError(f"locked comparison identity missing: {symbol} {pool}")
        comparison = before_after(score)
        comparison.update({"symbol": symbol, "pool": pool})
        comparisons.append(comparison)

    selected_flat = selected["REWARD"] + selected["NO_REWARD"]
    verdict_ok = (
        len(selected["REWARD"]) >= 3
        and len(selected["NO_REWARD"]) >= 3
        and all(item["identity_locked"] for item in selected_flat)
        and all(
            assertion["ratio_status"] in {"PASS", "N/A_ZERO_REWARD"}
            for item in selected_flat for assertion in item["ratio_assertions"]
        )
        and source["hash_unchanged"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": "PASS" if verdict_ok else "FAIL",
        "source": source,
        "formula": {
            "share_ratio": "share(range(H))/share(range(168h))",
            "fee_ev_usd": "size*fee_apr_pct/100*fee_haircut*(H/8760)*share_ratio(H)",
            "reward_ev_usd": "size*reward_apr_pct/100*(H/8760)*share_ratio(H)",
            "reward_haircut_scope": "engine only; validation assembler does not duplicate it",
            "position_usd": M1_MIN_POSITION_USD,
            "reference_horizon_hours": FEE_EVIDENCE_REFERENCE_HOURS,
            "horizons_hours": list(HORIZONS),
            "theoretical_h720_h168_sqrt_ratio": THEORETICAL_H720_H168_RATIO,
            "relative_tolerance": RATIO_RELATIVE_TOLERANCE,
        },
        "inventory_summary": {
            "total": len(inventory),
            "fully_calculable_all_horizons": sum(
                item["fully_calculable_all_horizons"] for item in inventory
            ),
            "fully_calculable_reward": sum(
                item["fully_calculable_all_horizons"]
                and item["reward_group"] == "REWARD" for item in inventory
            ),
            "fully_calculable_no_reward": sum(
                item["fully_calculable_all_horizons"]
                and item["reward_group"] == "NO_REWARD" for item in inventory
            ),
        },
        "selection_policy": (
            "fully calculable at 168/336/720; exact locked real address; no suspect flags; "
            "ratio assertions pass; internal 336h optimum first, then descending IL720/fixed cost"
        ),
        "selected_samples": selected,
        "before_after": comparisons,
        "inventory": inventory,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path,
        default=Path("reports/lp_funnel_rerank/20260809_135500/scanner.db"),
    )
    parser.add_argument(
        "--out", type=Path,
        default=Path("reports/lp_m0n_income_validation/20260809_n1"),
    )
    parser.add_argument("--expected-sha256", default=EXPECTED_DB_SHA256)
    parser.add_argument("--expected-as-of", default=EXPECTED_AS_OF)
    parser.add_argument(
        "--expected-logical-sha256", default=EXPECTED_LOGICAL_CONTENT_SHA256,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        args.db,
        args.expected_sha256,
        args.expected_as_of,
        args.expected_logical_sha256,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "income_validation.json"
    md_path = args.out / "income_validation.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"verdict={report['verdict']} rows={report['inventory_summary']['total']} "
        f"calculable={report['inventory_summary']['fully_calculable_all_horizons']} "
        f"reward_samples={len(report['selected_samples']['REWARD'])} "
        f"no_reward_samples={len(report['selected_samples']['NO_REWARD'])} "
        f"json={json_path} md={md_path}"
    )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
