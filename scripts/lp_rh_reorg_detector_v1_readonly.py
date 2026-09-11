#!/usr/bin/env python3
"""RH-02cj: offline reorg detector for the RH read-only pipeline.

Scans rh_market_states in the specified database for divergences:
  1. Same derived_block_number mapped to multiple distinct derived_block_hash
     (reorg divergences).
  2. Same derived_block_hash mapped to multiple distinct derived_block_number
     (data corruption, reported separately).

Default is read-only (reporting only, no database modification).
With --record-db <path>, divergences are idempotently registered into
rh_reorg_contested using ensure_table() and record_contested().

Never calls apply_rollback. Local operations only; no network requests.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_reorg_resolution_v1_readonly import (
    ensure_table as ensure_contested_table,
    record_contested,
)
from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH


@dataclass
class HashObservation:
    block_hash: str
    count: int
    first_seen: str
    last_seen: str


@dataclass
class ReorgDivergence:
    block_number: int
    hash_count: int
    hashes: List[HashObservation]
    overlap: bool


@dataclass
class HashNumberObservation:
    block_number: int
    count: int
    first_seen: str
    last_seen: str


@dataclass
class DataCorruption:
    block_hash: str
    number_count: int
    numbers: List[HashNumberObservation]


@dataclass
class ScanSummary:
    total_rows: int
    valid_rows: int
    skipped_null_rows: int
    min_block_number: Optional[int]
    max_block_number: Optional[int]
    min_sample_time: Optional[str]
    max_sample_time: Optional[str]
    divergence_count: int
    divergences: List[ReorgDivergence]
    corruption_count: int
    corruptions: List[DataCorruption]


def _check_overlap(hashes: List[HashObservation]) -> bool:
    if len(hashes) < 2:
        return False
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            h1 = hashes[i]
            h2 = hashes[j]
            # Two intervals [f1, l1] and [f2, l2] overlap if max(f1, f2) <= min(l1, l2)
            if max(h1.first_seen, h2.first_seen) <= min(h1.last_seen, h2.last_seen):
                return True
    return False


def scan_market_states(conn: sqlite3.Connection) -> ScanSummary:
    """Scan rh_market_states for block hash divergence and data corruption."""
    # Check if rh_market_states exists
    tbl_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rh_market_states'"
    ).fetchone()
    if not tbl_exists:
        return ScanSummary(
            total_rows=0,
            valid_rows=0,
            skipped_null_rows=0,
            min_block_number=None,
            max_block_number=None,
            min_sample_time=None,
            max_sample_time=None,
            divergence_count=0,
            divergences=[],
            corruption_count=0,
            corruptions=[],
        )

    # Basic stats
    total_rows = conn.execute("SELECT COUNT(*) FROM rh_market_states").fetchone()[0]

    valid_stats = conn.execute(
        """
        SELECT
            COUNT(*),
            MIN(derived_block_number),
            MAX(derived_block_number),
            MIN(sample_time),
            MAX(sample_time)
        FROM rh_market_states
        WHERE derived_block_number IS NOT NULL
          AND derived_block_hash IS NOT NULL
        """
    ).fetchone()

    valid_rows = valid_stats[0] or 0
    min_bn = valid_stats[1]
    max_bn = valid_stats[2]
    min_time = valid_stats[3]
    max_time = valid_stats[4]
    skipped_rows = total_rows - valid_rows

    # 1. Detect reorg divergence: same derived_block_number -> multiple distinct derived_block_hash
    divergence_rows = conn.execute(
        """
        SELECT
            derived_block_number,
            derived_block_hash,
            COUNT(*) as sample_count,
            MIN(sample_time) as first_seen,
            MAX(sample_time) as last_seen
        FROM rh_market_states
        WHERE derived_block_number IS NOT NULL
          AND derived_block_hash IS NOT NULL
        GROUP BY derived_block_number, derived_block_hash
        ORDER BY derived_block_number ASC, derived_block_hash ASC
        """
    ).fetchall()

    bn_map: Dict[int, List[HashObservation]] = {}
    for bn, b_hash, cnt, f_seen, l_seen in divergence_rows:
        bn_map.setdefault(bn, []).append(
            HashObservation(
                block_hash=b_hash,
                count=cnt,
                first_seen=f_seen,
                last_seen=l_seen,
            )
        )

    divergences: List[ReorgDivergence] = []
    for bn, hashes in bn_map.items():
        if len(hashes) > 1:
            divergences.append(
                ReorgDivergence(
                    block_number=bn,
                    hash_count=len(hashes),
                    hashes=hashes,
                    overlap=_check_overlap(hashes),
                )
            )

    # 2. Detect data corruption: same derived_block_hash -> multiple distinct derived_block_number
    corruption_rows = conn.execute(
        """
        SELECT
            derived_block_hash,
            derived_block_number,
            COUNT(*) as sample_count,
            MIN(sample_time) as first_seen,
            MAX(sample_time) as last_seen
        FROM rh_market_states
        WHERE derived_block_number IS NOT NULL
          AND derived_block_hash IS NOT NULL
        GROUP BY derived_block_hash, derived_block_number
        ORDER BY derived_block_hash ASC, derived_block_number ASC
        """
    ).fetchall()

    hash_map: Dict[str, List[HashNumberObservation]] = {}
    for b_hash, bn, cnt, f_seen, l_seen in corruption_rows:
        hash_map.setdefault(b_hash, []).append(
            HashNumberObservation(
                block_number=bn,
                count=cnt,
                first_seen=f_seen,
                last_seen=l_seen,
            )
        )

    corruptions: List[DataCorruption] = []
    for b_hash, numbers in hash_map.items():
        if len(numbers) > 1:
            corruptions.append(
                DataCorruption(
                    block_hash=b_hash,
                    number_count=len(numbers),
                    numbers=numbers,
                )
            )

    return ScanSummary(
        total_rows=total_rows,
        valid_rows=valid_rows,
        skipped_null_rows=skipped_rows,
        min_block_number=min_bn,
        max_block_number=max_bn,
        min_sample_time=min_time,
        max_sample_time=max_time,
        divergence_count=len(divergences),
        divergences=divergences,
        corruption_count=len(corruptions),
        corruptions=corruptions,
    )


def record_divergences_to_db(record_db_path: str | Path, divergences: List[ReorgDivergence]) -> int:
    """Register divergences into rh_reorg_contested in the specified record_db.

    Returns the number of pairs attempted/processed.
    """
    path = Path(record_db_path)
    conn = sqlite3.connect(str(path))
    try:
        ensure_contested_table(conn)
        total_recorded = 0
        for div in divergences:
            # Pairwise combinations of all divergent hashes for this block_number
            hashes = [h.block_hash for h in div.hashes]
            for h_a, h_b in itertools.combinations(sorted(hashes), 2):
                res = record_contested(conn, block_number=div.block_number, hash_a=h_a, hash_b=h_b)
                if res.get("created"):
                    total_recorded += 1
        return total_recorded
    finally:
        conn.close()


def generate_markdown_report(summary: ScanSummary) -> str:
    """Generate Chinese Markdown report conforming to RH-02cj spec."""
    lines: List[str] = []
    lines.append("# RH-02cj: 链分叉与重组 (Reorg) 离线检测报告")
    lines.append("")
    lines.append("## 1. 扫描范围")
    lines.append(f"- 总样本行数: `{summary.total_rows}`")
    lines.append(f"- 有效样本行数: `{summary.valid_rows}`")
    lines.append(f"- 跳过 NULL 样本行数: `{summary.skipped_null_rows}`")
    lines.append(f"- 区块高度区间: `{summary.min_block_number}` ~ `{summary.max_block_number}`")
    lines.append(f"- 时间区间: `{summary.min_sample_time}` ~ `{summary.max_sample_time}`")
    lines.append("")

    lines.append("## 2. 结论")
    if summary.divergence_count == 0:
        lines.append("- 分歧组数: `0`")
        lines.append("- 检测结果: **未发现分歧**")
    else:
        lines.append(f"- 分歧组数: `{summary.divergence_count}`")
        lines.append(f"- 检测结果: **发现 {summary.divergence_count} 组分歧**")
    lines.append("")

    lines.append("## 3. 分歧详情表")
    if summary.divergence_count == 0:
        lines.append("无分歧记录。")
    else:
        lines.append("| 区块高度 (block_number) | 涉及 Hash 数 | Hash 详情 (出现次数 / 首次时间 / 末次时间) | 观测窗口重叠 |")
        lines.append("|---|---|---|---|")
        for div in summary.divergences:
            hash_details = "<br>".join(
                [f"`{h.block_hash}`: {h.count}次 ({h.first_seen} ~ {h.last_seen})" for h in div.hashes]
            )
            overlap_str = "是" if div.overlap else "否"
            lines.append(f"| {div.block_number} | {div.hash_count} | {hash_details} | {overlap_str} |")
    lines.append("")

    lines.append("## 4. 数据损坏检查 (同一 Hash 对应多个高度)")
    if summary.corruption_count == 0:
        lines.append("- 损坏记录数: `0`")
        lines.append("- 状态: **未发现数据损坏**")
    else:
        lines.append(f"- 损坏记录数: `{summary.corruption_count}`")
        lines.append("- 状态: **发现数据损坏**（同一 block_hash 对应多个 block_number，非正常 reorg）")
        lines.append("")
        lines.append("| 区块 Hash (block_hash) | 涉及高度数 | 高度详情 (出现次数 / 首次时间 / 末次时间) |")
        lines.append("|---|---|---|")
        for corr in summary.corruptions:
            num_details = "<br>".join(
                [f"Block {n.block_number}: {n.count}次 ({n.first_seen} ~ {n.last_seen})" for n in corr.numbers]
            )
            lines.append(f"| `{corr.block_hash}` | {corr.number_count} | {num_details} |")
    lines.append("")

    lines.append("## 5. 局限性说明")
    lines.append(
        "本扫描只覆盖**已采集的样本**，采集器不回查历史块，所以一次深度小于采样间隔的 reorg 可能根本没被观测到。"
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RH-02cj: Reorg divergence offline detector.")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database to scan (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--out",
        help="Path to output markdown report",
    )
    parser.add_argument(
        "--record-db",
        help="Path to database where rh_reorg_contested will be written. If not set, only reports and does not write.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output scan results in JSON format to stdout.",
    )

    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        sys.stderr.write(f"Error: Database file does not exist: {db_path}\n")
        return 2

    # Connect strictly read-only to source db
    # Using URI mode=ro
    uri = f"file:{db_path.resolve()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except Exception as e:
        sys.stderr.write(f"Error connecting to {db_path}: {e}\n")
        return 2

    try:
        summary = scan_market_states(conn)
    except Exception as e:
        sys.stderr.write(f"Error scanning market states: {e}\n")
        return 2
    finally:
        conn.close()

    # Record to DB if requested
    if args.record_db:
        try:
            record_divergences_to_db(args.record_db, summary.divergences)
        except Exception as e:
            sys.stderr.write(f"Error recording to database {args.record_db}: {e}\n")
            return 2

    # Generate output
    report_md = generate_markdown_report(summary)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")

    if args.json:
        print(json.dumps(asdict(summary), indent=2, ensure_ascii=False))
    elif not args.out:
        print(report_md)

    # Exit code: 1 if divergences found; 0 if not; 2 on failure
    if summary.divergence_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())



