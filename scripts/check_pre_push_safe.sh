#!/usr/bin/env bash
# Pre-push safety checklist (per PUSH_AUTHORIZATION_CN.md §3).
#
# Verifies ONLY the files staged for commit (`git diff --cached --name-only`),
# not the entire working tree.  Historical untracked files (strategy pivot
# reports, funnel runs, long-horizon run logs from prior sessions) are
# deliberately not part of this RC and must NOT be staged or removed.
#
# Exits 0 only when every check passes; otherwise exits 1.

set -u

fail=0
ok() { printf '[OK]   %s\n' "$1"; }
bad() { printf '[FAIL] %s\n' "$1"; fail=$((fail+1)); }

# 1. Branch must be feat/prd-v2.1-m0-shadow
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" = "feat/prd-v2.1-m0-shadow" ]; then
    ok "branch = $branch"
else
    bad "branch = $branch (expected feat/prd-v2.1-m0-shadow)"
fi

# 2. No files staged yet
staged_count=$(git diff --cached --name-only | wc -l)
if [ "$staged_count" -eq 0 ]; then
    bad "no files staged — run 'git add <scope>' before this script"
fi

# 3. Every staged file must be in the RC scope
allowed_re='^(scripts/lp_rh_paper_daemon_entry_v1\.py|tests/test_lp_rh_paper_daemon_entry_v1\.py|scripts/lp_rh_paper_data_validity_v1\.py|tests/test_lp_rh_paper_data_validity_v1\.py|scripts/check_pre_push_safe\.sh|scripts/run_isolated_diagnostics\.sh|PAPER_MIN_RELEASE_V1_CN\.md|PAPER_START_REQUEST_CN\.md|BLOCKERS_20260914_RC_CN\.csv|ACCEPTANCE_MATRIX_20260914_CN\.md|PUSH_AUTHORIZATION_CN\.md|CONTINUOUS_AND_VARIANT_EVIDENCE_CN\.md|STAGE_A_REALDATA_SNAPSHOT\.json|READ_FIRST_20260914_CN\.md|FINAL_VERDICT_20260914_CN\.md|HANDOFF_20260914_CN\.md|OBSERVE_ONLY_DECISION_RULES_CN\.md|ACCEPTANCE_EVIDENCE_20260914_CN\.md|reports/lp_rh/release_candidate_[a-f0-9]+/(junit_full\.xml|audit_repro\.json|diagnostics_summary\.json|verify_junit_full\.xml|verify_audit_repro\.json|VERIFY_REPORT_CN\.md)|reports/lp_rh/STAGE_A_REALDATA_SNAPSHOT\.json)$'
while IFS= read -r path; do
    [ -z "$path" ] && continue
    if echo "$path" | grep -qE "$allowed_re"; then
        ok "scope: $path"
    else
        bad "out-of-scope staged file: $path"
    fi
done < <(git diff --cached --name-only)

# 4. No forbidden paths in staged set
forbidden='(\.github/workflows/.*\.yml|deploy/|k8s/|helm/|terraform/|\.k8s|fly\.toml|render\.yaml|vercel\.json|configs/config\.live\.toml|configs/config\.canary\.toml|\.env$|\.env\.runtime$|.*\.key$|.*\.pem$)'
hits=$(git diff --cached --name-only | grep -E "$forbidden" || true)
if [ -z "$hits" ]; then
    ok "no deployment/infra / secret files in staged set"
else
    bad "forbidden paths staged:"
    echo "$hits" | sed 's/^/    /'
fi

# 5. Working tree dirty files outside RC scope (informational, not blocking)
echo "---- informational ----"
echo "Untracked files outside RC scope (NOT staged, NOT removed):"
git ls-files --others --exclude-standard | grep -vE "$allowed_re" | head -10 | sed 's/^/  /'
untracked_outside=$(git ls-files --others --exclude-standard | grep -vcE "$allowed_re")
echo "  ... ($untracked_outside historical untracked file(s) total)"

if [ "$fail" -eq 0 ]; then
    echo
    echo "ALL CHECKS PASSED — safe to 'git commit' then 'git push origin feat/prd-v2.1-m0-shadow'"
    exit 0
else
    echo
    echo "$fail check(s) FAILED — DO NOT commit / push."
    exit 1
fi