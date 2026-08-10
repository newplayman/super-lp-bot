#!/usr/bin/env python3
"""Build TP-D D2/D4 comparisons from two scanner databases (READ-ONLY)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_funnel_autopsy_v1_readonly import (
    first_failed_gate,
    recomputed_accepted,
)


def load_latest(path: Path) -> tuple[str | None, list[dict[str, Any]]]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        stamp = connection.execute(
            "select max(as_of) from opportunity_scores"
        ).fetchone()[0]
        rows = [] if stamp is None else connection.execute(
            "select score_json from opportunity_scores where as_of=? order by id",
            (stamp,),
        ).fetchall()
    return stamp, [json.loads(raw) for (raw,) in rows]


def _identity(row: Mapping[str, Any]) -> str:
    return str(row.get("llama_pool_id") or row.get("resolved_pool") or row.get("pool") or "")


def _distribution(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts = Counter("null" if row.get(key) is None else f"{float(row[key]):.3f}" for row in rows)
    return dict(sorted(counts.items()))


def _terminal_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    values = Counter(first_failed_gate(row) or "ACCEPTED" for row in rows)
    return dict(sorted(values.items()))


def _best(rows: Sequence[Mapping[str, Any]], *, reached_netcover: bool) -> dict[str, Any] | None:
    eligible = [
        row for row in rows
        if isinstance(row.get("netcover_ratio"), (int, float))
        and (not reached_netcover or first_failed_gate(row) == "netcover")
    ]
    if not eligible:
        return None
    row = max(eligible, key=lambda item: float(item["netcover_ratio"]))
    return {
        "llama_pool_id": _identity(row),
        "symbol": row.get("symbol"),
        "netcover_ratio": row.get("netcover_ratio"),
        "first_failed_gate": first_failed_gate(row),
    }


def compare(old_rows: Sequence[Mapping[str, Any]], new_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    controlled = [row for row in new_rows if "same_batch_former_stable" in row]
    pass_to_fail, fail_to_pass = [], []
    for row in controlled:
        former, current = bool(row["same_batch_former_stable"]), bool(row.get("stable"))
        if former == current:
            continue
        item = {
            "llama_pool_id": _identity(row),
            "symbol": row.get("symbol"),
            "former_6_enter_frac": row.get("same_batch_former_enter_frac"),
            "current_10_enter_frac": row.get("enter_frac"),
            "former_6_n_enter": row.get("same_batch_former_n_enter"),
        }
        (pass_to_fail if former else fail_to_pass).append(item)

    old_by_id = {_identity(row): row for row in old_rows if _identity(row)}
    new_by_id = {_identity(row): row for row in new_rows if _identity(row)}
    intersection = sorted(set(old_by_id) & set(new_by_id))
    terminal_changes = []
    for identity in intersection:
        old_gate = first_failed_gate(old_by_id[identity]) or "ACCEPTED"
        new_gate = first_failed_gate(new_by_id[identity]) or "ACCEPTED"
        if old_gate != new_gate:
            terminal_changes.append({
                "llama_pool_id": identity,
                "symbol": new_by_id[identity].get("symbol"),
                "old_first_failed_gate": old_gate,
                "new_first_failed_gate": new_gate,
            })

    return {
        "schema": "lp_tp_d_compare_v1",
        "thresholds_unchanged": {"stable_min_frac": 0.7, "netcover_min": 1.0},
        "old_count": len(old_rows),
        "new_count": len(new_rows),
        "same_batch_d2": {
            "controlled_count": len(controlled),
            "former_6_enter_frac_distribution": _distribution(
                controlled, "same_batch_former_enter_frac"
            ),
            "current_10_enter_frac_distribution": _distribution(controlled, "enter_frac"),
            "former_6_stable_count": sum(bool(row["same_batch_former_stable"]) for row in controlled),
            "current_10_stable_count": sum(bool(row.get("stable")) for row in controlled),
            "pass_to_fail": pass_to_fail,
            "fail_to_pass": fail_to_pass,
        },
        "cross_run_d4": {
            "intersection_count": len(intersection),
            "old_terminal_distribution": _terminal_distribution(old_rows),
            "new_terminal_distribution": _terminal_distribution(new_rows),
            "terminal_gate_changes_on_intersection": terminal_changes,
            "old_accepted": sum(recomputed_accepted(row) for row in old_rows),
            "new_accepted": sum(recomputed_accepted(row) for row in new_rows),
            "old_best_reached_netcover": _best(old_rows, reached_netcover=True),
            "new_best_reached_netcover": _best(new_rows, reached_netcover=True),
            "old_best_any_calculable": _best(old_rows, reached_netcover=False),
            "new_best_any_calculable": _best(new_rows, reached_netcover=False),
        },
    }


def _flip_table(items: Sequence[Mapping[str, Any]]) -> list[str]:
    if not items:
        return ["| — | — | — | — |", ""]
    return [
        f"| {item.get('symbol')} | `{item.get('llama_pool_id')}` | "
        f"{item.get('former_6_enter_frac')} | {item.get('current_10_enter_frac')} |"
        for item in items
    ] + [""]


def render_markdown(payload: Mapping[str, Any]) -> str:
    d2, d4 = payload["same_batch_d2"], payload["cross_run_d4"]
    lines = [
        "# TP-D D2/D4 对照",
        "",
        "阈值保持不变：`STABLE_MIN_FRAC=0.7`、`NetCover>=1.0`。D2 翻转来自同一批 10 窗观测的前 6 窗反事实，因此不混入时点变化。",
        "",
        f"- D2 可控样本：{d2['controlled_count']}；6 窗 stable={d2['former_6_stable_count']}，10 窗 stable={d2['current_10_stable_count']}。",
        f"- D4 old/new：{payload['old_count']}/{payload['new_count']}；交集 {d4['intersection_count']}。",
        f"- accepted：{d4['old_accepted']} → {d4['new_accepted']}。",
        "",
        "## D2 6窗过 → 10窗不过",
        "",
        "| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |",
        "|---|---|---:|---:|",
        *_flip_table(d2["pass_to_fail"]),
        "## D2 6窗不过 → 10窗过",
        "",
        "| symbol | llama_pool_id | 6窗 enter_frac | 10窗 enter_frac |",
        "|---|---|---:|---:|",
        *_flip_table(d2["fail_to_pass"]),
        "## 分布与 D4 逐闸",
        "",
        f"- 6窗 enter_frac：`{json.dumps(d2['former_6_enter_frac_distribution'], sort_keys=True)}`",
        f"- 10窗 enter_frac：`{json.dumps(d2['current_10_enter_frac_distribution'], sort_keys=True)}`",
        f"- old 逐闸：`{json.dumps(d4['old_terminal_distribution'], sort_keys=True)}`",
        f"- new 逐闸：`{json.dumps(d4['new_terminal_distribution'], sort_keys=True)}`",
        f"- 交集 first-failed-gate 变化：{len(d4['terminal_gate_changes_on_intersection'])}（完整列表见 JSON）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-db", type=Path, required=True)
    parser.add_argument("--new-db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    old_stamp, old_rows = load_latest(args.old_db)
    new_stamp, new_rows = load_latest(args.new_db)
    payload = compare(old_rows, new_rows)
    payload["sources"] = {
        "old_db": str(args.old_db), "old_as_of": old_stamp,
        "new_db": str(args.new_db), "new_as_of": new_stamp,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "D2_D4_COMPARISON.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / "D2_D4_COMPARISON.md").write_text(
        render_markdown(payload), encoding="utf-8"
    )
    print(json.dumps({
        "old": len(old_rows), "new": len(new_rows),
        "controlled": payload["same_batch_d2"]["controlled_count"],
        "flips": len(payload["same_batch_d2"]["pass_to_fail"]) + len(payload["same_batch_d2"]["fail_to_pass"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
