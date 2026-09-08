"""Repo-wide guard: a module that imports `scripts.*` must bootstrap sys.path.

pytest puts the repo root on sys.path itself, so a module missing its own
bootstrap passes every test and then dies with ModuleNotFoundError the first
time it is run as a script.  lp_rh_organic_recorder shipped that way and only
failed when it was started as a daemon.
"""
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = sorted((REPO_ROOT / "scripts").glob("lp_rh_*.py"))

_IMPORTS_SCRIPTS = re.compile(r"^\s*(from|import)\s+scripts\.", re.M)
_BOOTSTRAPS = re.compile(r"sys\.path\.insert\(\s*0\s*,\s*str\(REPO_ROOT\)\s*\)")


def test_scripts_dir_is_not_empty():
    assert len(SCRIPTS) > 20, "expected the RH module set to be present"


def test_every_module_importing_scripts_bootstraps_sys_path():
    missing = []
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8")
        if _IMPORTS_SCRIPTS.search(text) and not _BOOTSTRAPS.search(text):
            missing.append(path.name)
    assert not missing, (
        "these modules import scripts.* without putting the repo root on "
        f"sys.path, so they run under pytest and die as scripts: {missing}")
