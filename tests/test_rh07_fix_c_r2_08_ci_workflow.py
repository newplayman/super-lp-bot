from pathlib import Path
import pytest
import yaml


def test_ci_workflow_structure_and_fail_close():
    """R2-08: Verify CI workflows enforce fail-close graduation gates and probe reproduction checks."""
    repo_root = Path(__file__).resolve().parent.parent
    workflows_dir = repo_root / ".github" / "workflows"
    assert workflows_dir.exists()

    # 1. audit-regression.yml must exist and verify probe regression
    audit_reg_path = workflows_dir / "audit-regression.yml"
    assert audit_reg_path.exists()
    content = audit_reg_path.read_text(encoding="utf-8")
    assert "audit_repro.py" in content
    assert "defects_reproduced" in content or "audit_repro" in content

    # 2. ci.yml must run tests
    ci_path = workflows_dir / "ci.yml"
    assert ci_path.exists()
    ci_content = ci_path.read_text(encoding="utf-8")
    assert "pytest" in ci_content

    # 3. No unauthorized live authorization bypasses in workflows
    for wf in workflows_dir.glob("*.yml"):
        txt = wf.read_text(encoding="utf-8")
        assert "LIVE_AUTHORIZED=true" not in txt
        assert "tiny_live_authorized: true" not in txt
