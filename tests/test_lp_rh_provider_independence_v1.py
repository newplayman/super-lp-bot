"""Tests for lp_rh_provider_independence_v1."""
from pathlib import Path
from unittest import mock
import pytest

from scripts.lp_rh_provider_independence_v1 import check_independence, render_report


def _make_mock_response(status_code=200, content=b'{"jsonrpc":"2.0"}', issuer_cn="TestCA"):
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.content = content
    sock = mock.MagicMock()
    sock.getpeercert.return_value = {
        "issuer": ((("commonName", issuer_cn),),),
        "subjectAltName": (("DNS", "example.com"),),
    }
    resp.raw.connection.sock = sock
    return resp


def test_check_independence_two_distinct_endpoints():
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if "alpha" in host:
            return [(2, 1, 6, "", ("1.1.1.1", 443))]
        return [(2, 1, 6, "", ("2.2.2.2", 443))]

    perf_times = []
    for _ in range(5):
        perf_times.extend([0.0, 0.010])  # 10ms for alpha
    for _ in range(5):
        perf_times.extend([0.0, 0.050])  # 50ms for beta

    def mock_get(url, *args, **kwargs):
        return _make_mock_response(status_code=200, issuer_cn="CA-Alpha" if "alpha" in url else "CA-Beta")

    with mock.patch("socket.getaddrinfo", side_effect=mock_getaddrinfo), \
         mock.patch("requests.get", side_effect=mock_get), \
         mock.patch("time.perf_counter", side_effect=perf_times):
        res = check_independence("https://alpha.rpc.io", "https://beta.rpc.io")

    assert res["independent"] is True
    assert res["evidence"]["dns"]["shared_ips"] == []
    assert res["evidence"]["latency_ms"]["too_close"] is False
    assert res["evidence"]["certs"]["shared_issuer_cn"] is False


def test_check_independence_same_ip_fails():
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("10.0.0.1", 443))]

    with mock.patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
        res = check_independence("https://provider-a.com", "https://provider-b.com")

    assert res["independent"] is False
    assert "DNS" in res["reason"]
    assert "10.0.0.1" in res["evidence"]["dns"]["shared_ips"]


def test_check_independence_latency_too_close():
    def mock_getaddrinfo(host, port, *args, **kwargs):
        if "first" in host:
            return [(2, 1, 6, "", ("1.1.1.1", 443))]
        return [(2, 1, 6, "", ("2.2.2.2", 443))]

    perf_times = []
    for _ in range(10):
        perf_times.extend([0.0, 0.020])

    with mock.patch("socket.getaddrinfo", side_effect=mock_getaddrinfo), \
         mock.patch("requests.get", return_value=_make_mock_response()), \
         mock.patch("time.perf_counter", side_effect=perf_times):
        res = check_independence("https://first.rpc.com", "https://second.rpc.com")

    assert res["independent"] is False
    assert "latency cluster" in res["reason"].lower()
    assert res["evidence"]["latency_ms"]["too_close"] is True


def test_render_report_writes_markdown(tmp_path):
    report_file = tmp_path / "report.md"
    sample_res = {
        "independent": True,
        "reason": "Endpoints are independent",
        "evidence": {
            "dns": {"provider_a_ips": ["1.1.1.1"], "provider_b_ips": ["2.2.2.2"], "shared_ips": []},
            "latency_ms": {"provider_a": [10.0], "provider_b": [30.0], "median_a": 10.0, "median_b": 30.0, "diff_pct": 66.6, "too_close": False},
            "certs": {"provider_a": {"issuer_cn": "CA1"}, "provider_b": {"issuer_cn": "CA2"}, "shared_issuer_cn": False},
            "chain_id_responses": {
                "provider_a": [{"status_code": 200, "latency_ms": 10.0, "fingerprint": "abc"}],
                "provider_b": [{"status_code": 200, "latency_ms": 30.0, "fingerprint": "def"}],
            },
        },
    }
    render_report(sample_res, providers=["https://prov1.io", "https://prov2.io"], out_path=report_file)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Independent:" in content
    assert "DNS" in content
    assert "latency" in content.lower()
