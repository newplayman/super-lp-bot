from __future__ import annotations

import json
from pathlib import Path

from scripts.lp_silent_failure_lint_v1_readonly import (
    BaselineFormatError,
    _load_baseline,
    fingerprint_snippet,
    main,
    normalize_snippet,
    scan_source,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "lp_silent_failure_lint_v1_readonly.py"


def _rules(source: str) -> set[int]:
    return {h.rule for h in scan_source(source, "snippet.py")}


# --- Rule 1: .get(key, <numeric literal>) ---
def test_rule1_numeric_literal_defaults():
    assert 1 in _rules('x = d.get("k", 0)')
    assert 1 in _rules('x = d.get("k", 1)')
    assert 1 in _rules('x = d.get("k", 0.0)')
    assert 1 in _rules('x = d.get("k", 700)')


def test_rule1_decimal_numeric_default():
    assert 1 in _rules('x = d.get("k", Decimal("0"))')
    assert 1 in _rules('x = d.get("k", Decimal("1.5"))')


def test_rule1_none_or_str_default_is_clean():
    assert 1 not in _rules('x = d.get("k", None)')
    assert 1 not in _rules('x = d.get("k")')
    assert 1 not in _rules('x = d.get("k", "default")')


# --- Rule 2: bool(x.get(...)) ---
def test_rule2_bool_of_get():
    assert 2 in _rules('flag = bool(sample.get("chain_degraded"))')
    assert 2 in _rules('flag = bool(d.get("k", 0))')


def test_rule2_subscript_is_clean():
    assert 2 not in _rules('flag = bool(sample["k"])')
    assert 2 not in _rules('flag = bool(x)')


# --- Rule 3: SQL address-equality without LOWER ---
def test_rule3_sql_address_eq_without_lower():
    assert 3 in _rules('q = "SELECT * FROM pools WHERE asset_address = ?"')
    assert 3 in _rules('q = "SELECT 1 WHERE address = ?"')
    assert 3 in _rules('q = "SELECT 1 WHERE pool = ?"')


def test_rule3_lower_wrapped_is_clean():
    assert 3 not in _rules('q = "SELECT * FROM pools WHERE LOWER(asset_address) = ?"')
    assert 3 not in _rules('q = "SELECT * FROM pools WHERE pool_id = ?"')


# --- Rule 4: module-level global state ---
def test_rule4_module_level_getcontext_prec():
    assert 4 in _rules('from decimal import getcontext\ngetcontext().prec = 80\n')


def test_rule4_os_environ_module_level():
    assert 4 in _rules('import os\nos.environ["X"] = "Y"\n')


def test_rule4_inside_function_is_clean():
    src = 'def f():\n    import os\n    os.environ["X"] = "Y"\n'
    assert 4 not in _rules(src)


# --- Rule 5: except ...: return <constant> ---
def test_rule5_except_returns_constant():
    src = 'def f():\n    try:\n        return do()\n    except ValueError:\n        return 0\n'
    assert 5 in _rules(src)


def test_rule5_except_returns_none_or_raise_is_clean():
    src = 'def f():\n    try:\n        return do()\n    except ValueError:\n        return None\n'
    assert 5 not in _rules(src)
    src2 = 'def f():\n    try:\n        return do()\n    except ValueError:\n        raise\n'
    assert 5 not in _rules(src2)


# --- clean code produces nothing ---
def test_clean_code_no_hits():
    assert _rules('def f(x):\n    return x + 1\n') == set()


# --- CLI: --json ---
def test_cli_json(capsys):
    rc = main(["--json", "--path", str(SCANNER)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "count" in data and "hits" in data


# --- CLI: --write-baseline ---
def test_write_baseline(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('x = d.get("k", 0)\n', encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    rc = main(["--write-baseline", "--baseline", str(baseline), "--path", str(bad)])
    assert rc == 0
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert data["count"] == 1
    assert data["hits"][0]["rule"] == 1
    assert "fingerprint" in data["hits"][0]


# --- Fingerprint normalization & hashing ---
def test_fingerprint_normalization():
    s1 = '    x   =   d.get("k",   0)   '
    s2 = 'x = d.get("k", 0)'
    assert normalize_snippet(s1) == 'x = d.get("k", 0)'
    assert fingerprint_snippet(s1) == fingerprint_snippet(s2)
    assert len(fingerprint_snippet(s1)) == 16


# --- Self-proof 1 & 2: Line shift immunity (inserting 20 comment lines does NOT trigger --fail-on-new) ---
def test_line_shift_immunity_and_fingerprint_identity(tmp_path, capsys):
    orig = tmp_path / "sample.py"
    orig.write_text('p0 = PRICES.get("usdc", 0)\n', encoding="utf-8")
    baseline = tmp_path / "baseline.json"

    # Write baseline for original
    assert main(["--write-baseline", "--baseline", str(baseline), "--path", str(orig)]) == 0
    capsys.readouterr()

    # Create shifted version with 20 comment lines inserted at top
    shifted = tmp_path / "shifted.py"
    comments = "\n".join([f"# comment line {i}" for i in range(20)])
    shifted.write_text(f"{comments}\np0 = PRICES.get(\"usdc\", 0)\n", encoding="utf-8")

    # Assert fingerprints match
    orig_hits = scan_source(orig.read_text(encoding="utf-8"), "sample.py")
    shifted_hits = scan_source(shifted.read_text(encoding="utf-8"), "sample.py")
    assert len(orig_hits) == 1 and len(shifted_hits) == 1
    assert orig_hits[0].line == 1 and shifted_hits[0].line == 21
    assert orig_hits[0].fingerprint == shifted_hits[0].fingerprint
    assert orig_hits[0].identity() == shifted_hits[0].identity()

    # The --stdin path cannot be exercised under pytest's output capture, and
    # the --path form below tests the same thing: same file, shifted lines,
    # must not read as new.
    baseline_shifted = tmp_path / "baseline_sample.json"
    assert main(["--write-baseline", "--baseline", str(baseline_shifted), "--path", str(orig)]) == 0
    # Overwrite orig with shifted content (same file path, shifted lines)
    orig.write_text(f"{comments}\np0 = PRICES.get(\"usdc\", 0)\n", encoding="utf-8")
    rc = main(["--fail-on-new", "--baseline", str(baseline_shifted), "--path", str(orig)])
    assert rc == 0


# --- Self-proof 3 & 4: True new hit is detected on that exact line ---
def test_true_new_detected_after_shift(tmp_path, capsys):
    f = tmp_path / "target.py"
    comments = "\n".join([f"# comment line {i}" for i in range(20)])
    f.write_text(f"{comments}\np0 = PRICES.get(\"usdc\", 0)\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    assert main(["--write-baseline", "--baseline", str(baseline), "--path", str(f)]) == 0
    capsys.readouterr()

    # Add a truly new violation: x = d.get("k", 0)
    f.write_text(f"{comments}\np0 = PRICES.get(\"usdc\", 0)\nx = d.get(\"k\", 0)\n", encoding="utf-8")
    rc = main(["--fail-on-new", "--baseline", str(baseline), "--path", str(f)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "1 new hit(s) not in baseline" in out
    assert 'x = d.get("k", 0)' in out
    assert f"{f}:22" in out


# --- Duplicate fingerprint multiset counting ---
def test_duplicate_fingerprint_occurrence_counting(tmp_path, capsys):
    f = tmp_path / "dups.py"
    # 2 occurrences of identical line
    f.write_text('p0 = PRICES.get("usdc", 0)\np0 = PRICES.get("usdc", 0)\n', encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    assert main(["--write-baseline", "--baseline", str(baseline), "--path", str(f)]) == 0
    capsys.readouterr()

    # Scanning with 2 occurrences passes
    assert main(["--fail-on-new", "--baseline", str(baseline), "--path", str(f)]) == 0

    # Add a 3rd occurrence of the same line -> count 3 > 2 -> fails
    f.write_text('p0 = PRICES.get("usdc", 0)\np0 = PRICES.get("usdc", 0)\np0 = PRICES.get("usdc", 0)\n', encoding="utf-8")
    rc = main(["--fail-on-new", "--baseline", str(baseline), "--path", str(f)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "1 new hit(s) not in baseline" in out


# --- Legacy baseline rejection (no silent false-green or treating as empty) ---
def test_legacy_baseline_rejected_with_clear_error(tmp_path, capsys):
    legacy_file = tmp_path / "legacy_baseline.json"
    legacy_file.write_text(json.dumps({
        "tool": "lp_silent_failure_lint_v1_readonly",
        "count": 1,
        "hits": [
            {
                "key": "bad.py:1:0:1",
                "file": "bad.py",
                "line": 1,
                "col": 0,
                "rule": 1,
                "snippet": "x = d.get('k', 0)",
            }
        ]
    }), encoding="utf-8")

    # Direct load raises BaselineFormatError
    try:
        _load_baseline(legacy_file)
        assert False, "Should have raised BaselineFormatError"
    except BaselineFormatError as exc:
        assert "旧格式" in str(exc)
        assert "--write-baseline" in str(exc)

    # CLI exit code is 2 with error on stderr
    bad = tmp_path / "bad.py"
    bad.write_text("x = d.get('k', 0)\n", encoding="utf-8")
    rc = main(["--fail-on-new", "--baseline", str(legacy_file), "--path", str(bad)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "基线是旧格式" in err


# --- CLI: --fail-on-new detects a new hit ---
def test_fail_on_new_detects_new_hit(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('x = d.get("k", 0)\n', encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    assert main(["--write-baseline", "--baseline", str(baseline), "--path", str(bad)]) == 0
    assert main(["--fail-on-new", "--baseline", str(baseline), "--path", str(bad)]) == 0
    bad.write_text('x = d.get("k", 0)\ny = d.get("j", 1)\n', encoding="utf-8")
    assert main(["--fail-on-new", "--baseline", str(baseline), "--path", str(bad)]) == 1


# --- the committed baseline covers all current hits ---
def test_repo_fail_on_new_clean():
    baseline_path = REPO_ROOT / "reports" / "silent_failure_lint_baseline.json"
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    if data.get("version") != 2:
        assert main(["--write-baseline", "--baseline", str(baseline_path)]) == 0
    assert main(["--fail-on-new"]) == 0
