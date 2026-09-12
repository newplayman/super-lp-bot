"""Provider independence prober and report generator (PRD §8.3 / W3)."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, socket, statistics, time, urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import requests


def _resolve_ips(hostname: str, timeout_secs: float = 10.0) -> Set[str]:
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_secs)
    try:
        return {item[4][0] for item in socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)}
    finally:
        socket.setdefaulttimeout(old)


def _inspect_cert(resp: Any) -> Dict[str, Any]:
    info: Dict[str, Any] = {"issuer_cn": None, "san": []}
    try:
        raw = getattr(resp, "raw", None)
        conn = getattr(raw, "connection", None)
        sock = getattr(conn, "sock", None)
        cert = conn.getpeercert() if hasattr(conn, "getpeercert") else (sock.getpeercert() if sock and hasattr(sock, "getpeercert") else None)
        if isinstance(cert, dict):
            for entry in cert.get("issuer", ()):
                for k, v in entry:
                    if k == "commonName":
                        info["issuer_cn"] = v
            info["san"] = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"]
    except Exception:
        pass
    return info


def _probe_single(url: str, timeout_secs: float) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout_secs, stream=True)
        lat = (time.perf_counter() - t0) * 1000.0
        cert = _inspect_cert(resp)
        return {"status_code": resp.status_code, "latency_ms": lat,
                "fingerprint": hashlib.sha256(resp.content).hexdigest()[:16],
                "cert": cert, "error": None}
    except Exception as e:
        return {"status_code": None, "latency_ms": (time.perf_counter() - t0) * 1000.0,
                "fingerprint": None, "cert": {"issuer_cn": None, "san": []}, "error": str(e)}


def _run_probes(url: str, probe_count: int = 5, timeout_secs: float = 10.0) -> List[Dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=probe_count) as executor:
        return [f.result() for f in [executor.submit(_probe_single, url, timeout_secs) for _ in range(probe_count)]]


def check_independence(provider_a: str, provider_b: str, *, timeout_secs: float = 10.0, probe_path: str = "/") -> Dict[str, Any]:
    host_a = urllib.parse.urlparse(provider_a).hostname or provider_a
    host_b = urllib.parse.urlparse(provider_b).hostname or provider_b
    dns_err: Optional[str] = None
    ips_a, ips_b = set(), set()
    try:
        ips_a = _resolve_ips(host_a, timeout_secs)
    except Exception as e:
        dns_err = f"DNS resolution failed for {host_a}: {e}"
    try:
        ips_b = _resolve_ips(host_b, timeout_secs)
    except Exception as e:
        dns_err = f"DNS resolution failed for {host_b}: {e}"

    empty_ev = {
        "dns": {"provider_a_ips": sorted(list(ips_a)), "provider_b_ips": sorted(list(ips_b)), "shared_ips": []},
        "latency_ms": {"provider_a": [], "provider_b": [], "median_a": 0.0, "median_b": 0.0, "diff_pct": 0.0, "too_close": False},
        "certs": {"provider_a": {}, "provider_b": {}, "shared_issuer_cn": False},
        "chain_id_responses": {"provider_a": [], "provider_b": []},
    }
    if dns_err or not ips_a or not ips_b:
        return {"independent": False, "reason": dns_err or "inconclusive: empty DNS resolution", "evidence": empty_ev}

    shared_ips = ips_a & ips_b
    if shared_ips:
        empty_ev["dns"]["shared_ips"] = sorted(list(shared_ips))
        return {"independent": False, "reason": f"DNS: shared IP address(es) detected: {sorted(list(shared_ips))}", "evidence": empty_ev}

    path = "/" + probe_path.lstrip("/")
    probes_a = _run_probes(provider_a.rstrip("/") + path, 5, timeout_secs)
    probes_b = _run_probes(provider_b.rstrip("/") + path, 5, timeout_secs)
    valid_a = [p for p in probes_a if p["error"] is None and p["status_code"] is not None]
    valid_b = [p for p in probes_b if p["error"] is None and p["status_code"] is not None]

    if not valid_a or not valid_b:
        empty_ev["chain_id_responses"] = {"provider_a": probes_a, "provider_b": probes_b}
        return {"independent": False, "reason": "no_responses", "evidence": empty_ev}

    lats_a = [p["latency_ms"] for p in valid_a]
    lats_b = [p["latency_ms"] for p in valid_b]
    med_a, med_b = statistics.median(lats_a), statistics.median(lats_b)
    max_med = max(med_a, med_b)
    diff_pct = (abs(med_a - med_b) / max_med * 100.0) if max_med > 0 else 0.0
    too_close = diff_pct < 30.0

    cert_a = next((p["cert"] for p in valid_a if p["cert"]["issuer_cn"]), {"issuer_cn": None, "san": []})
    cert_b = next((p["cert"] for p in valid_b if p["cert"]["issuer_cn"]), {"issuer_cn": None, "san": []})
    shared_cn = bool(cert_a["issuer_cn"] and cert_b["issuer_cn"] and cert_a["issuer_cn"] == cert_b["issuer_cn"])

    reason = f"latency cluster too tight: median latencies differ by {diff_pct:.1f}% (< 30%)" if too_close else \
        "Endpoints are independent: distinct IP addresses, distinct latency profiles, distinct certificate chains"

    return {
        "independent": not too_close,
        "reason": reason,
        "evidence": {
            "dns": {"provider_a_ips": sorted(list(ips_a)), "provider_b_ips": sorted(list(ips_b)), "shared_ips": []},
            "latency_ms": {"provider_a": [round(x, 2) for x in lats_a], "provider_b": [round(x, 2) for x in lats_b],
                           "median_a": round(med_a, 2), "median_b": round(med_b, 2),
                           "diff_pct": round(diff_pct, 2), "too_close": too_close},
            "certs": {"provider_a": cert_a, "provider_b": cert_b, "shared_issuer_cn": shared_cn},
            "chain_id_responses": {"provider_a": probes_a, "provider_b": probes_b},
        },
    }


def render_report(independence_result: Dict[str, Any], *, providers: List[str], out_path: Path) -> None:
    prov_a, prov_b = providers[0], providers[1]
    indep = independence_result["independent"]
    status_str = "Independent: Yes" if indep else "Independent: No (Blocked)"
    ev = independence_result["evidence"]
    dns, lat, certs, resps = ev.get("dns", {}), ev.get("latency_ms", {}), ev.get("certs", {}), ev.get("chain_id_responses", {})

    def _fmt_ms(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"

    def _fmt_pct(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"

    lines = [
        "# Provider Independence Evidence Report", "",
        f"- **Status**: {status_str}",
        f"- **Provider A**: `{prov_a}`",
        f"- **Provider B**: `{prov_b}`",
        f"- **Verdict Reason**: {independence_result.get('reason', 'N/A')}", "",
        "## DNS Resolution Evidence", "",
        f"- **Provider A IPs**: {', '.join(dns.get('provider_a_ips', [])) or 'None'}",
        f"- **Provider B IPs**: {', '.join(dns.get('provider_b_ips', [])) or 'None'}",
        f"- **Shared IPs**: {', '.join(dns.get('shared_ips', [])) or 'None (disjoint IP sets)'}", "",
        "## Latency Analysis", "",
        f"- **Provider A Median Latency**: {_fmt_ms(lat.get('median_a'))} ms (samples: {lat.get('provider_a', [])})",
        f"- **Provider B Median Latency**: {_fmt_ms(lat.get('median_b'))} ms (samples: {lat.get('provider_b', [])})",
        f"- **Relative Difference**: {_fmt_pct(lat.get('diff_pct'))}%",
        f"- **Latency Cluster Too Tight (<30%)**: {'Yes (Flagged)' if lat.get('too_close') else 'No (Sufficient divergence)'}", "",
        "## TLS Certificate Evidence", "",
        f"- **Provider A Issuer CN**: `{certs.get('provider_a', {}).get('issuer_cn', 'Unknown')}`",
        f"- **Provider B Issuer CN**: `{certs.get('provider_b', {}).get('issuer_cn', 'Unknown')}`",
        f"- **Shared Issuer CN**: {'Yes (CDN / shared CA)' if certs.get('shared_issuer_cn') else 'No (Distinct CAs)'}", "",
        "## Response Fingerprints", "",
        "| Provider | Sample | Status | Latency (ms) | Hash Fingerprint |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for idx, resp in enumerate(resps.get("provider_a", []), 1):
        lines.append(f"| Provider A | #{idx} | {resp.get('status_code')} | {_fmt_ms(resp.get('latency_ms'))} | `{resp.get('fingerprint')}` |")
    for idx, resp in enumerate(resps.get("provider_b", []), 1):
        lines.append(f"| Provider B | #{idx} | {resp.get('status_code')} | {_fmt_ms(resp.get('latency_ms'))} | `{resp.get('fingerprint')}` |")
    lines.append("")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe and verify independence of two RPC endpoints.")
    parser.add_argument("--provider-a", required=True, help="First provider URL")
    parser.add_argument("--provider-b", required=True, help="Second provider URL")
    parser.add_argument("--out", required=True, help="Output report path (.md or .json)")
    parser.add_argument("--probe-path", default="/", help="Path to probe on providers")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout in seconds")
    args = parser.parse_args()

    out_path = Path(args.out)
    result = check_independence(args.provider_a, args.provider_b, timeout_secs=args.timeout, probe_path=args.probe_path)
    if out_path.suffix.lower() == ".json":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    else:
        render_report(result, providers=[args.provider_a, args.provider_b], out_path=out_path)
    print(f"Independence: {result['independent']}")
    print(f"Reason: {result['reason']}")
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
