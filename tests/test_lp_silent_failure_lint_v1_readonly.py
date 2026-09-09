from __future__ import annotations

import json
from pathlib import Path

from scripts.lp_silent_failure_lint_v1_readonly import main, scan_source

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
    assert data["count"] == 1 and data["hits"][0]["rule"] == 1


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
    assert main(["--fail-on-new"]) == 0
