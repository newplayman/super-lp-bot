"""FIX-D2: 0.70 stays fixed while ten windows restore literal semantics."""
from scripts.lp_multiwindow_stability_v1_readonly import (
    DEFAULT_N_WINDOWS,
    STABLE_MIN_FRAC,
    classify_stability,
)
from scripts.lp_scanner_daemon_v1_readonly import DefaultStages, _parser


class NoNetworkRpcPool:
    def call(self, *_args, **_kwargs):
        raise AssertionError("constructor must not make network calls")

    def health_snapshot(self):
        return {"state": "NORMAL"}


def test_scanner_and_stability_module_share_ten_window_default():
    assert DEFAULT_N_WINDOWS == 10
    assert _parser().parse_args([]).n_windows == DEFAULT_N_WINDOWS
    assert DefaultStages(rpc_pool=NoNetworkRpcPool()).n_windows == DEFAULT_N_WINDOWS


def test_stability_threshold_is_unchanged_and_literal_at_ten_windows():
    assert STABLE_MIN_FRAC == 0.7
    seven_of_ten = classify_stability([1.0] * 7 + [0.0] * 3)
    six_of_ten = classify_stability([1.0] * 6 + [0.0] * 4)
    assert seven_of_ten == {
        "n_windows": 10,
        "n_enter": 7,
        "enter_frac": 0.7,
        "stable": True,
    }
    assert six_of_ten["enter_frac"] == 0.6
    assert six_of_ten["stable"] is False


def test_six_window_measurement_reproduces_old_discretization_distortion():
    four_of_six = classify_stability([1.0] * 4 + [0.0] * 2)
    five_of_six = classify_stability([1.0] * 5 + [0.0])
    assert four_of_six["enter_frac"] == 0.667 and four_of_six["stable"] is False
    assert five_of_six["enter_frac"] == 0.833 and five_of_six["stable"] is True
