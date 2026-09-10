#!/usr/bin/env python3
"""lp_silent_failure_lint_v1_readonly — AST scanner for the "silent false-green" family.

RH-02be. Scans scripts/*.py (or a single file / stdin) and reports five defect
patterns that produce plausible-looking numbers while silently invalidating the
conclusion. Read-only: parses source with ast, never executes it, never touches
wallets or chain state.

Rules:
  1  .get(key, <numeric literal>) tolerant default on an economic path
  2  bool(x.get("key")) risk gate that is always False when the key is absent
  3  SQL "<address/pool/hash> = ?" without LOWER() (EIP-55 case mismatch)
  4  module-level global-state mutation (getcontext().prec / locale / warnings /
     sys.setrecursionlimit / os.environ[...])
  5  except ...: return <constant> (error disguised as a normal value)

Usage:
  python scripts/lp_silent_failure_lint_v1_readonly.py            # human table
  ... --json                                                     # structured
  ... --fail-on-new [--baseline PATH]                            # CI gate
  ... --write-baseline [--baseline PATH]                         # (re)generate baseline
  ... --path FILE   /   ... --stdin --name LABEL                 # single source
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

RULES = {
    1: "经济计算路径上的宽容数值默认值 (.get(key, <numeric>))",
    2: "bool(x.get('key')) 形式的风险判断",
    3: "SQL 地址/哈希大小写敏感等值比较 (缺 LOWER())",
    4: "模块级全局状态修改 (getcontext().prec / locale / warnings / sys / os.environ)",
    5: "except 吞异常后返回常量数值",
}

WHY = {
    1: "缺数据被当成数值 0/1/魔数，经济量被静默算错",
    2: "键缺失时 bool(None)=False，风险闸门恒判安全",
    3: "EVM 地址有 EIP-55 校验和大小写，未 LOWER() 会漏匹配合法地址",
    4: "import 即改全局状态，测试单独跑绿、全量跑红",
    5: "异常被吞掉后返回常量，错误伪装成正常数值",
}

# A "clean" decimal literal: optional sign, digits (optional fraction), optional exponent.
# Rejects NaN/inf so Decimal("NaN") is not treated as a numeric default.
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
# SQL: <...address.../...hash.../pool> = ?  (case-insensitive; \bpool avoids pool_id)
_ADDR_EQ_RE = re.compile(r"(?i)\b(\w*address\w*|\w*hash\w*|pool)\s*=\s*\?")
_LOWER_RE = re.compile(r"(?i)\blower\s*\(")
_WS_COLLAPSE_RE = re.compile(r"\s+")


def normalize_snippet(text: str) -> str:
    """Strip outer whitespace and collapse internal consecutive whitespace to a single space."""
    return _WS_COLLAPSE_RE.sub(" ", text.strip())


def fingerprint_snippet(text: str) -> str:
    """Normalized snippet sha256 prefix (16 hex chars)."""
    norm = normalize_snippet(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


@dataclass
class Hit:
    file: str
    line: int
    col: int
    rule: int
    snippet: str
    why: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = fingerprint_snippet(self.snippet)

    def identity(self) -> tuple[str, int, str]:
        """Content-based identity: (relative_file_path, rule, normalized_fingerprint)."""
        return (self.file, self.rule, self.fingerprint)

    def key(self) -> str:
        """Display key (file:line:col:rule) preserved for backwards-compatible presentation."""
        return f"{self.file}:{self.line}:{self.col}:{self.rule}"

    def to_dict(self) -> dict:
        return asdict(self)


def _is_numeric_constant(node: ast.AST) -> bool:
    """True if node is a bare numeric literal (int/float; excludes bool/None/str)."""
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool) or v is None:
            return False
        return isinstance(v, (int, float))
    return False


def _is_decimal_numeric_call(node: ast.AST) -> bool:
    """True if node is Decimal('<clean number>') with a single numeric-string arg."""
    if not isinstance(node, ast.Call) or len(node.args) != 1:
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else (
        func.attr if isinstance(func, ast.Attribute) else None)
    if name != "Decimal":
        return False
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return bool(_NUM_RE.match(arg.value.strip()))
    return False


def _is_numeric_default(node: ast.AST) -> bool:
    return _is_numeric_constant(node) or _is_decimal_numeric_call(node)


def _sql_address_eq_without_lower(s: str) -> bool:
    return bool(_ADDR_EQ_RE.search(s)) and not bool(_LOWER_RE.search(s))


def _is_getcontext_attr_assign(target: ast.AST) -> bool:
    """target is getcontext().<attr> (follow the .value chain down to getcontext())."""
    if not isinstance(target, ast.Attribute):
        return False
    cur = target.value
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    return (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name)
            and cur.func.id == "getcontext")


def _is_os_environ_subscript(target: ast.AST) -> bool:
    """target is os.environ[...] (Subscript whose value is the os.environ attribute)."""
    if not isinstance(target, ast.Subscript):
        return False
    val = target.value
    return (isinstance(val, ast.Attribute) and val.attr == "environ"
            and isinstance(val.value, ast.Name) and val.value.id == "os")


def _is_module_call(call: ast.AST, module: str, func: str) -> bool:
    if not isinstance(call, ast.Call):
        return False
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr == func
            and isinstance(f.value, ast.Name) and f.value.id == module)


def _is_rule4(node: ast.AST) -> bool:
    """Module-level global-state mutation (rule 4)."""
    if isinstance(node, (ast.Assign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if _is_getcontext_attr_assign(t) or _is_os_environ_subscript(t):
                return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        c = node.value
        if (_is_module_call(c, "locale", "setlocale")
                or _is_module_call(c, "warnings", "filterwarnings")
                or _is_module_call(c, "sys", "setrecursionlimit")):
            return True
    return False


def _module_level_nodes(tree: ast.Module):
    """Yield statements at module level (not inside def/class), descending into
    top-level compound statements (if/try/with/for/while) but not into defs/classes."""
    def rec(body):
        for stmt in body:
            yield stmt
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for field in ("body", "orelse", "finalbody", "handlers"):
                sub = getattr(stmt, field, None)
                if isinstance(sub, list):
                    yield from rec(sub)
    yield from rec(tree.body)


def _is_return_constant(node: ast.AST) -> bool:
    """A literal value (not None) returned from an except handler."""
    return isinstance(node, ast.Constant) and node.value is not None


def scan_source(source: str, filename: str) -> list[Hit]:
    """Parse one source string and return all rule hits (empty list on SyntaxError)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    lines = source.splitlines()

    def snippet(node: ast.AST) -> str:
        ln = getattr(node, "lineno", 0)
        if 0 < ln <= len(lines):
            return lines[ln - 1].strip()[:100]
        return ""

    hits: list[Hit] = []

    # Rule 1: .get(key, <numeric literal>)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and len(node.args) >= 2
                and _is_numeric_default(node.args[1])):
            hits.append(Hit(filename, node.lineno, node.col_offset, 1,
                            snippet(node), WHY[1]))

    # Rule 2: bool(x.get(...))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "bool" and len(node.args) == 1):
            inner = node.args[0]
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "get"):
                hits.append(Hit(filename, node.lineno, node.col_offset, 2,
                                snippet(node), WHY[2]))

    # Rule 3: SQL address-equality without LOWER()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and _sql_address_eq_without_lower(node.value)):
            hits.append(Hit(filename, node.lineno, node.col_offset, 3,
                            snippet(node), WHY[3]))

    # Rule 4: module-level global-state mutation
    for node in _module_level_nodes(tree):
        if _is_rule4(node):
            hits.append(Hit(filename, node.lineno, node.col_offset, 4,
                            snippet(node), WHY[4]))

    # Rule 5: except ...: return <constant>
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            for stmt in node.body:
                if (isinstance(stmt, ast.Return) and stmt.value is not None
                        and _is_return_constant(stmt.value)):
                    hits.append(Hit(filename, stmt.lineno, stmt.col_offset, 5,
                                    snippet(stmt), WHY[5]))
                    break

    return hits


def _label(p: Path, root: Path | None) -> str:
    """Repo-relative label when p is under root, else the path as given."""
    if root is not None:
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    return str(p)


def scan_files(paths: list[Path], root: Path | None = None) -> list[Hit]:
    """Scan .py files on disk and return all hits, sorted by (file, line, col, rule)."""
    hits: list[Hit] = []
    for p in paths:
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(scan_source(source, _label(p, root)))
    hits.sort(key=lambda h: (h.file, h.line, h.col, h.rule))
    return hits


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_baseline(root: Path) -> Path:
    return root / "reports" / "silent_failure_lint_baseline.json"


class BaselineFormatError(ValueError):
    """Raised when baseline format is outdated or invalid."""
    pass


def _load_baseline(path: Path) -> Counter[tuple[str, int, str]]:
    """Load baseline and return counter of (file, rule, fingerprint).

    Raises FileNotFoundError if baseline path does not exist.
    Raises BaselineFormatError if file is legacy (lacks fingerprint or version != 2).
    """
    if not path.exists():
        raise FileNotFoundError(f"baseline file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineFormatError(f"invalid JSON in baseline {path}: {exc}") from exc

    # The v1 baseline was a bare list, so data.get() raises AttributeError on
    # it rather than reporting a format problem -- and an uncaught crash that
    # still exits 0 reads as "no new hits", which is exactly the failure mode
    # this tool exists to catch.
    if not isinstance(data, dict):
        raise BaselineFormatError(
            f"baseline {path} is the legacy list format (no fingerprints). "
            f"Re-generate with --write-baseline."
        )

    version = data.get("version")
    hits_raw = data.get("hits")
    if hits_raw is None or not isinstance(hits_raw, list):
        raise BaselineFormatError(
            f"baseline {path} missing 'hits' list. Re-generate with --write-baseline."
        )

    # Legacy detection: version < 2 or missing "fingerprint" on hits
    if version != 2:
        raise BaselineFormatError(
            f"基线是旧格式（version={version!r}，缺指纹字段），"
            f"请使用 --write-baseline 重新生成：python scripts/lp_silent_failure_lint_v1_readonly.py --write-baseline"
        )

    counts: Counter[tuple[str, int, str]] = Counter()
    for item in hits_raw:
        fp = item.get("fingerprint")
        f = item.get("file")
        r = item.get("rule")
        if not fp or f is None or r is None:
            raise BaselineFormatError(
                f"基线包含缺少 fingerprint/file/rule 的旧条目: {item}. "
                f"请使用 --write-baseline 重新生成。"
            )
        counts[(f, int(r), str(fp))] += 1
    return counts


def find_new_hits(hits: list[Hit], baseline_counts: Counter[tuple[str, int, str]]) -> list[Hit]:
    """Find hits that exceed baseline counts for (file, rule, fingerprint)."""
    seen: Counter[tuple[str, int, str]] = Counter()
    new_hits: list[Hit] = []
    for h in hits:
        ident = h.identity()
        seen[ident] += 1
        if seen[ident] > baseline_counts.get(ident, 0):
            new_hits.append(h)
    return new_hits


def _write_baseline(path: Path, hits: list[Hit]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "tool": "lp_silent_failure_lint_v1_readonly",
        "identity_schema": "(file, rule, fingerprint)",
        "note": ("Baseline of known silent-failure hits matched by content fingerprint. "
                 "--fail-on-new blocks any hit exceeding baseline occurrence count. "
                 "Line numbers are for display only. Regenerate after an approved fix."),
        "count": len(hits),
        "hits": [
            {
                "file": h.file,
                "line": h.line,
                "col": h.col,
                "rule": h.rule,
                "fingerprint": h.fingerprint,
                "snippet": h.snippet,
                "key": h.key(),
            }
            for h in hits
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _print_table(hits: list[Hit]) -> None:
    if not hits:
        print("no silent-failure patterns found")
        return
    print(f"{'RULE':<5} {'LOCATION':<55} SNIPPET")
    print("-" * 100)
    for h in hits:
        print(f"{h.rule:<5} {f'{h.file}:{h.line}':<55} {h.snippet}")
    print("-" * 100)
    print(f"{len(hits)} hit(s). Why each rule is dangerous:")
    for rule in sorted({h.rule for h in hits}):
        print(f"  rule {rule}: {WHY[rule]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="AST scanner for the silent-failure (silent false-green) family.")
    ap.add_argument("--json", action="store_true", help="emit structured JSON")
    ap.add_argument("--fail-on-new", action="store_true",
                    help="exit non-zero if any hit is not in the baseline")
    ap.add_argument("--write-baseline", action="store_true",
                    help="write current hits to the baseline file")
    ap.add_argument("--baseline", default=None, help="baseline path")
    ap.add_argument("--path", default=None, help="scan a single file on disk")
    ap.add_argument("--stdin", action="store_true", help="read source from stdin")
    ap.add_argument("--name", default="<stdin>", help="label for --stdin source")
    ap.add_argument("--root", default=None, help="repo root (default: auto-detect)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else _default_root()
    baseline_path = Path(args.baseline) if args.baseline else _default_baseline(root)

    if args.stdin:
        hits = scan_source(sys.stdin.read(), args.name)
    elif args.path:
        hits = scan_files([Path(args.path)], root=root)
    else:
        hits = scan_files(sorted((root / "scripts").glob("*.py")), root=root)

    if args.write_baseline:
        _write_baseline(baseline_path, hits)
        print(f"wrote baseline with {len(hits)} hit(s) -> {baseline_path}")
        return 0

    if args.fail_on_new:
        try:
            known_counts = _load_baseline(baseline_path)
        except (FileNotFoundError, BaselineFormatError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 2

        new = find_new_hits(hits, known_counts)
        if args.json:
            print(json.dumps({
                "count": len(hits), "new_count": len(new),
                "hits": [h.to_dict() for h in hits],
                "new": [h.to_dict() for h in new],
            }, ensure_ascii=False, indent=2))
        else:
            _print_table(hits)
            print(f"\n--fail-on-new: {len(new)} new hit(s) not in baseline "
                  f"({baseline_path})")
            for h in new:
                print(f"  NEW rule {h.rule}  {h.file}:{h.line}  [{h.fingerprint}]  {h.snippet}")
        return 1 if new else 0

    if args.json:
        print(json.dumps({"count": len(hits),
                          "hits": [h.to_dict() for h in hits]},
                         ensure_ascii=False, indent=2))
    else:
        _print_table(hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
