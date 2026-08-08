"""Contracts for the exact M0 legacy environment-bound node quarantine."""

from conftest import LEGACY_ENVIRONMENT_BOUND_NODEIDS


EXPECTED_NODEIDS = {
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_a_v2_supervisor_pid_still_alive",
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_h_generator_sample_partial_sample_true",
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_no_collector_restart_since_audit",
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_v2_data_dir_unchanged",
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_v2_report_dir_unchanged",
    "tests/test_lp_continuous_staged_observation_and_coverage_report_v1.py::test_generator_runs_on_v2_data",
    "tests/test_lp_long_horizon_r1_12h_real_data_observation_v1.py::test_r1_12h_completed",
    "tests/test_lp_long_horizon_readonly_collector_6h_real_wallclock_v2.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_collector_smoke_v1.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_collector_6h_run_approval_v1.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_data_pipeline_v1.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_collector_6h_real_wallclock_v1.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_collector_fix_repeat_v1.py::test_no_canary_live_paper_keypair_process",
    "tests/test_lp_long_horizon_readonly_collector_staged_request_v1.py::test_no_canary_live_paper_keypair_process",
}


def test_quarantine_is_exactly_fourteen_nodeids_not_files_or_globs():
    assert set(LEGACY_ENVIRONMENT_BOUND_NODEIDS) == EXPECTED_NODEIDS
    assert len(LEGACY_ENVIRONMENT_BOUND_NODEIDS) == 14
    assert all("::test_" in nodeid for nodeid in LEGACY_ENVIRONMENT_BOUND_NODEIDS)
    assert all("*" not in nodeid for nodeid in LEGACY_ENVIRONMENT_BOUND_NODEIDS)


def test_every_quarantined_node_has_specific_environment_reason():
    reasons = list(LEGACY_ENVIRONMENT_BOUND_NODEIDS.values())
    assert all(reason.startswith("legacy environment-bound: ") for reason in reasons)
    assert sum("retired PID 3872268" in reason for reason in reasons) == 2
    assert sum("completed 6/6" in reason for reason in reasons) == 4
    assert sum("COMPRESSED_PASS" in reason for reason in reasons) == 1
    assert sum("protected read-only paper PID 1349731" in reason for reason in reasons) == 7
