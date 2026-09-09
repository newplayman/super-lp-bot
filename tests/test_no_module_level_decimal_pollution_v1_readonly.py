import ast
import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def test_no_module_level_decimal_prec_pollution():
    """RH-02ax regression guard: Ensure scripts/*.py does not modify getcontext().prec at module level."""
    assert SCRIPTS_DIR.is_dir(), f"scripts directory not found: {SCRIPTS_DIR}"

    violations = []
    re_pattern = re.compile(r"^\s*getcontext\(\)\.prec\s*=")

    for py_file in sorted(SCRIPTS_DIR.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")

        # 1. Regex check on lines
        for idx, line in enumerate(source.splitlines(), start=1):
            if re_pattern.search(line):
                violations.append(f"{py_file.name}:{idx} matches regex: {line.strip()}")

        # 2. AST check: Find any Assign/AugAssign target that is `getcontext().prec`
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    # target is getcontext().prec -> Attribute(value=Call(func=Name(id='getcontext')), attr='prec')
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "prec"
                        and isinstance(target.value, ast.Call)
                        and isinstance(target.value.func, ast.Name)
                        and target.value.func.id == "getcontext"
                    ):
                        violations.append(
                            f"{py_file.name}:{node.lineno} AST found getcontext().prec assignment"
                        )

    assert not violations, "Found module-level getcontext().prec pollution:\n" + "\n".join(violations)
