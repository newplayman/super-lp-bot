"""T56 guard (RH-02z): replay of the old Base snapshot must match the approved golden baseline exactly.

PRD §20 T56: 旧Base模型同一SQLite快照新旧计算 → 未批准的逐闸结果差异=0.
The replay capability already exists (scripts/lp_netcover_snapshot_replay_v1_readonly.py);
this test turns it into standing regression evidence: any future change to the NetCover
gates that alters the verdict on the old Base snapshot turns this test red.

The baseline tests/fixtures/rh/t56_base_replay_golden.json was generated once, by a human,
and committed.  The test must NEVER auto-write the baseline — every baseline change
must be an explicit human decision.  No network, no wallet, no write to the source
DB (read-only, verified by md5).
"""
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/opt/lpbot/lp-bot-v3-origin-check")

import pytest

from scripts.lp_netcover_snapshot_replay_v1_readonly import replay

CODE_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
SNAPSHOT = CODE_ROOT / "reports" / "lp_m0f_acceptance" / "20260809" / "scanner.db"
GOLDEN = CODE_ROOT / "tests" / "fixtures" / "rh" / "t56_base_replay_golden.json"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _stable_value(value):
    """Normalize one value: floats become 17-significant-digit strings, else pass through."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float cannot enter the baseline: {value!r}")
        return format(value, ".17g")
    return value


def normalize_replay(result: dict) -> dict:
    """Drop environment fields (code_root/db), sort rows by a stable key, floats to fixed strings."""
    rows = [{k: _stable_value(v) for k, v in row.items()} for row in result["rows"]]
    rows.sort(key=lambda r: (str(r.get("as_of", "")), str(r.get("pool", "")), int(r.get("id", 0))))
    return {
        "row_count": result["row_count"],
        "netcover_pass_counts": result["netcover_pass_counts"],
        "position_cap_counts": result["position_cap_counts"],
        "rows": rows,
    }


def _load_golden() -> dict:
    """Load the baseline; on missing file fail with a human-review hint, never auto-write it."""
    if not GOLDEN.is_file():
        raise AssertionError(
            f"基线缺失: {GOLDEN} — 基线缺失，需人工审核后生成；测试不得自动写入基线"
        )
    payload = json.loads(GOLDEN.read_text())
    if not isinstance(payload, dict):
        raise AssertionError(f"golden top level must be a dict, got {type(payload).__name__}")
    return payload


def _diff_rows(golden_rows, actual_rows):
    diffs = []
    if len(golden_rows) != len(actual_rows):
        diffs.append(f"rows length differs: golden={len(golden_rows)} actual={len(actual_rows)}")
    for index in range(min(len(golden_rows), len(actual_rows))):
        g_row, a_row = golden_rows[index], actual_rows[index]
        label = (f"row[{index}] as_of={g_row.get('as_of')} pool={g_row.get('pool')} "
                 f"id={g_row.get('id')}")
        for field in sorted(set(g_row) | set(a_row)):
            if field not in g_row:
                diffs.append(f"{label} field '{field}' only in actual: {a_row[field]!r}")
            elif field not in a_row:
                diffs.append(f"{label} field '{field}' only in golden: {g_row[field]!r}")
            elif g_row[field] != a_row[field]:
                diffs.append(f"{label} field '{field}' differs: golden={g_row[field]!r} "
                             f"actual={a_row[field]!r}")
    return diffs


def _diff_report(golden: dict, actual: dict):
    """Field-by-field diff: a list of human-readable 'which field, which row' descriptions."""
    diffs = []
    for key in sorted(set(golden) | set(actual)):
        if key not in golden:
            diffs.append(f"top-level key '{key}' only in actual: {actual[key]!r}")
        elif key not in actual:
            diffs.append(f"top-level key '{key}' only in golden: {golden[key]!r}")
        elif key == "rows":
            diffs.extend(_diff_rows(golden["rows"], actual["rows"]))
        elif golden[key] != actual[key]:
            diffs.append(f"top-level field '{key}' differs: golden={golden[key]!r} "
                         f"actual={actual[key]!r}")
    return diffs


@pytest.fixture(scope="module")
def replay_result():
    return replay(db_path=SNAPSHOT, code_root=CODE_ROOT)


class TestT56Prerequisites:
    def test_snapshot_exists_and_nonempty(self):
        assert SNAPSHOT.is_file(), f"快照缺失: {SNAPSHOT}（T56 基线依赖此只读快照）"
        assert SNAPSHOT.stat().st_size > 0, f"快照为空: {SNAPSHOT}"

    def test_golden_is_valid_json_dict(self):
        assert isinstance(_load_golden(), dict)

    def test_golden_has_no_code_root_key(self):
        assert "code_root" not in _load_golden(), "golden 不得固化本机 code_root 路径"

    def test_golden_has_no_db_key(self):
        assert "db" not in _load_golden(), "golden 不得固化本机 db 绝对路径"


class TestT56AnchoredValues:
    def test_row_count_is_30(self, replay_result):
        assert replay_result["row_count"] == 30

    def test_netcover_pass_counts_all_false(self, replay_result):
        assert replay_result["netcover_pass_counts"] == {"False": 30}

    def test_position_cap_counts_14_false_16_true(self, replay_result):
        assert replay_result["position_cap_counts"] == {"False": 14, "True": 16}


class TestT56ZeroDrift:
    def test_replay_matches_golden_field_by_field(self, replay_result):
        """★ T56「差异=0」: normalized replay is field-by-field equal to the approved baseline."""
        golden = _load_golden()
        actual = normalize_replay(replay_result)
        diffs = _diff_report(golden, actual)
        assert not diffs, (
            "T56 差异 != 0：未批准的逐闸结果差异（相对 golden 基线）:\n" + "\n".join(diffs)
        )

    def test_source_db_md5_unchanged_by_replay(self):
        """★ 只读: snapshot file md5 is identical before and after replay."""
        before = _md5(SNAPSHOT)
        replay(db_path=SNAPSHOT, code_root=CODE_ROOT)
        after = _md5(SNAPSHOT)
        assert before == after, f"源库被改动: md5 before={before} after={after}"

    def test_two_consecutive_replays_are_identical(self, replay_result):
        fresh = normalize_replay(replay(db_path=SNAPSHOT, code_root=CODE_ROOT))
        assert fresh == normalize_replay(replay_result), "连续两次 replay 结果不一致（非确定性）"


class TestT56NormalizationAndFailureModes:
    def test_float_normalization_is_stable(self):
        samples = [0.18018168808097274, 1.1755537764102791e-05, 0.0,
                   -0.00016991914162750452, 123456.789]
        for value in samples:
            assert _stable_value(value) == _stable_value(value), f"浮点规范化不稳定: {value!r}"
            assert isinstance(_stable_value(value), str)
        # 同一数值、不同字面量形式，规范化到同一字符串
        assert _stable_value(0.5) == _stable_value(1 / 2)

    def test_replay_missing_db_raises_identifiable_error(self):
        missing = CODE_ROOT / "reports" / "no_such_t56_snapshot.db"
        with pytest.raises(sqlite3.OperationalError) as excinfo:
            replay(db_path=missing, code_root=CODE_ROOT)
        assert "unable to open" in str(excinfo.value)

    def test_missing_golden_fails_with_human_review_message(self, tmp_path, monkeypatch):
        fake = tmp_path / "t56_base_replay_golden.json"
        monkeypatch.setattr(sys.modules[__name__], "GOLDEN", fake)
        with pytest.raises(AssertionError) as excinfo:
            _load_golden()
        message = str(excinfo.value)
        assert "基线缺失" in message and "人工审核" in message
        assert not fake.exists(), "测试不得自动写入基线"
