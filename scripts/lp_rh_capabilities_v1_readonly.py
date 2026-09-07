#!/usr/bin/env python3
"""RH chain capability matrix and provider probe (read-only, offline-testable).

Issues only JSON-RPC read methods (chainId, blockNumber, getBlockByNumber,
clientVersion, eth_call, eth_getLogs, eth_estimateGas, eth_getCode); never
signs, broadcasts, or touches wallets; imports no web3/eth_account/solana/
requests. Capability is not a boolean: each key resolves to
VERIFIED|UNVERIFIED|UNSUPPORTED|DEGRADED with evidence (url + block_number)
and expires_at (fetched_at + 24h). The shared RpcPool CHAINS table is NOT
modified; provider endpoints are injected. Offline: every public function is
exercisable from an injected ``rpc`` callable or a local JSON fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID, SEED_ADDRESSES  # noqa: E402

# --- capability vocabulary -------------------------------------------------
CAPABILITY_KEYS = [
    "discovery", "state_read", "history_read", "fee_attribution",
    "add_quote", "remove_quote", "swap_quote", "simulate",
    "unsigned_build", "broadcast", "reconcile",
]
VERIFIED, UNVERIFIED, UNSUPPORTED, DEGRADED = (
    "VERIFIED", "UNVERIFIED", "UNSUPPORTED", "DEGRADED",
)

# WETH decimals() selector.
_WETH_DECIMALS_SELECTOR = "0x313ce567"
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"
_WETH = SEED_ADDRESSES["WETH"]["address"]
_USER_AGENT = "curl/8.5.0"
_TIMEOUT = 10

@dataclass
class ProviderProbe:
    url: str
    chain_id_hex: Optional[str] = None
    block_number: Optional[int] = None
    block_hash: Optional[str] = None
    client_version: Optional[str] = None
    supports_eth_call: bool = False
    supports_get_logs: bool = False
    supports_estimate_gas: bool = False
    error: Optional[str] = None
    fetched_at: Optional[str] = None

# --- small helpers ---------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _add_24h(iso_ts: Optional[str]) -> Optional[str]:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (dt + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

def _hex_to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    except (ValueError, TypeError):
        return None

def _call(rpc: Callable, method: str, params: list):
    """Invoke rpc and split the JSON-RPC envelope into (value, error).

    A response carrying a non-null ``error`` field is returned as
    (None, <error text>) and must never be treated as a 0/empty result (T12).
    """
    try:
        resp = rpc(method, params)
    except Exception as exc:  # transport / decode failure
        return None, "RPC_EXCEPTION: %s" % str(exc)
    if isinstance(resp, dict) and resp.get("error") is not None:
        try:
            err_text = json.dumps(resp["error"])
        except (TypeError, ValueError):
            err_text = str(resp["error"])
        return None, "JSONRPC_ERROR: %s" % err_text
    if isinstance(resp, dict):
        return resp.get("result"), None
    return resp, None

def _default_rpc(url: str) -> Callable:
    """urllib-backed JSON-RPC client. Sets User-Agent curl/8.5.0 (Cloudflare
    403s the default Python-urllib agent) and a 10s timeout."""
    def rpc(method: str, params: list):
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json",
                     "User-Agent": _USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return rpc

def _fixture_rpc(fixture: object) -> Callable:
    """Replay fixed responses from a fixture dict. eth_call may be keyed by
    ``eth_call:<data>`` first, then by bare ``eth_call``."""
    responses = fixture.get("responses", {}) if isinstance(fixture, dict) else {}
    if not isinstance(responses, dict):
        responses = {}

    def rpc(method: str, params: list):
        if method == "eth_call" and isinstance(params, list) and params \
                and isinstance(params[0], dict):
            data = params[0].get("data", "")
            key = "eth_call:%s" % data
            if key in responses:
                return responses[key]
        if method in responses:
            return responses[method]
        return {"jsonrpc": "2.0", "id": 0,
                "error": {"code": -32601, "message": "method not in fixture"}}
    return rpc

# --- provider probe --------------------------------------------------------
def probe_provider(url: str, rpc: Optional[Callable] = None,
                   weth_address: str = _WETH,
                   fetched_at: Optional[str] = None) -> ProviderProbe:
    """Probe one endpoint. Core calls (chainId, blockNumber, getBlockByNumber)
    stop on the first JSON-RPC error (recorded in ``error``); capability
    probes tolerate errors (flag stays False, client_version stays None)."""
    if rpc is None:
        rpc = _default_rpc(url)
    probe = ProviderProbe(url=url, fetched_at=fetched_at or _now_iso())

    value, err = _call(rpc, "eth_chainId", [])
    if err:
        probe.error = err
        return probe
    probe.chain_id_hex = value

    value, err = _call(rpc, "eth_blockNumber", [])
    if err:
        probe.error = err
        return probe
    probe.block_number = _hex_to_int(value)

    value, err = _call(rpc, "eth_getBlockByNumber", ["latest", False])
    if err:
        probe.error = err
        return probe
    if isinstance(value, dict):
        probe.block_hash = value.get("hash")

    value, err = _call(rpc, "web3_clientVersion", [])
    if err is None:
        probe.client_version = value

    value, err = _call(
        rpc, "eth_call",
        [{"to": weth_address, "data": _WETH_DECIMALS_SELECTOR}, "latest"])
    if err is None and value not in (None, "0x", ""):
        probe.supports_eth_call = True

    value, err = _call(
        rpc, "eth_getLogs",
        [{"fromBlock": "latest", "toBlock": "latest", "address": weth_address}])
    if err is None:
        probe.supports_get_logs = True

    value, err = _call(
        rpc, "eth_estimateGas",
        [{"from": _ZERO_ADDR, "to": _ZERO_ADDR, "value": "0x0"}])
    if err is None:
        probe.supports_estimate_gas = True

    return probe

# --- chain identity gate ---------------------------------------------------
def chain_identity_gate(probe: ProviderProbe,
                        expected_chain_id: int = RH_CHAIN_ID) -> str:
    """CHAIN_ID_OK when the probed chainId equals expected; CHAIN_ID_MISMATCH
    for any other concrete value (e.g. 46630 testnet, 1 mainnet);
    CHAIN_ID_UNKNOWN when it could not be read (T01)."""
    if probe.chain_id_hex is None:
        return "CHAIN_ID_UNKNOWN"
    actual = _hex_to_int(probe.chain_id_hex)
    if actual is None:
        return "CHAIN_ID_UNKNOWN"
    if actual == expected_chain_id:
        return "CHAIN_ID_OK"
    return "CHAIN_ID_MISMATCH"

# --- provider independence -------------------------------------------------
def _host_of(url: str) -> str:
    host = url.split("://", 1)[1] if "://" in url else url
    host = host.split("/", 1)[0]
    host = host.split("@", 1)[-1]
    host = host.split(":", 1)[0]
    return host.lower()

def _domain_body(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else host

def provider_independence(probes: List[ProviderProbe]) -> Dict[str, object]:
    """Assess whether two providers are independent backends (T11, T13).

    same client_version + synced block_hash + same/alias host -> False,
    SAME_BACKEND_SUSPECTED; same height but divergent block_hash -> None,
    BLOCK_HASH_DIVERGENCE; different host + (hash consistent at same height
    OR height diff <= 2) -> True, DISTINCT_BACKENDS; else None, INCONCLUSIVE.
    """
    if len(probes) < 2:
        return {"independent": None, "reason": "INSUFFICIENT_PROVIDERS"}
    a, b = probes[0], probes[1]
    host_a, host_b = _host_of(a.url), _host_of(b.url)
    same_host = host_a == host_b
    alias = (not same_host) and _domain_body(host_a) == _domain_body(host_b)
    same_backend_host = same_host or alias
    same_version = (a.client_version is not None
                    and a.client_version == b.client_version)
    same_hash = (a.block_hash is not None and a.block_hash == b.block_hash)
    same_height = (a.block_number is not None
                   and a.block_number == b.block_number)

    if same_height and a.block_hash is not None and b.block_hash is not None \
            and a.block_hash != b.block_hash:
        return {"independent": None, "reason": "BLOCK_HASH_DIVERGENCE"}
    if same_backend_host and same_version and same_hash:
        return {"independent": False, "reason": "SAME_BACKEND_SUSPECTED"}
    if not same_backend_host:
        height_diff = None
        if a.block_number is not None and b.block_number is not None:
            height_diff = abs(a.block_number - b.block_number)
        if same_hash or (height_diff is not None and height_diff <= 2):
            return {"independent": True, "reason": "DISTINCT_BACKENDS"}
    return {"independent": None, "reason": "INCONCLUSIVE"}

# --- capability matrix -----------------------------------------------------
def build_capability_matrix(probes: List[ProviderProbe],
                            protocol_flags: Dict[str, object]) -> Dict[str, dict]:
    """Per-venue matrix for uniswap_v3@4663 and uniswap_v4@4663.
    discovery/state_read VERIFIED when >=1 provider is CHAIN_ID_OK and
    supports eth_call; history_read follows supports_get_logs; all other keys
    stay UNVERIFIED. V4 is all UNSUPPORTED when v4_state_view_address is empty."""
    ok_probes = [p for p in probes if chain_identity_gate(p) == "CHAIN_ID_OK"]
    any_call = any(p.supports_eth_call for p in ok_probes)
    any_logs = any(p.supports_get_logs for p in ok_probes)
    evidence_probe = ok_probes[0] if ok_probes else (probes[0] if probes else None)
    evidence = None
    expires_at = None
    if evidence_probe is not None:
        evidence = {"url": evidence_probe.url,
                    "block_number": evidence_probe.block_number}
        expires_at = _add_24h(evidence_probe.fetched_at)

    def entry(status: str) -> dict:
        return {"status": status, "evidence": evidence, "expires_at": expires_at}

    matrix: Dict[str, dict] = {}
    for venue in ("uniswap_v3@4663", "uniswap_v4@4663"):
        is_v4 = venue.startswith("uniswap_v4")
        entries: Dict[str, dict] = {}
        if is_v4 and not protocol_flags.get("v4_state_view_address"):
            for key in CAPABILITY_KEYS:
                entries[key] = entry(UNSUPPORTED)
        else:
            for key in CAPABILITY_KEYS:
                if key in ("discovery", "state_read"):
                    entries[key] = entry(VERIFIED if any_call else UNVERIFIED)
                elif key == "history_read":
                    entries[key] = entry(VERIFIED if any_logs else UNVERIFIED)
                else:
                    entries[key] = entry(UNVERIFIED)
        matrix[venue] = entries
    return matrix

def _probe_summary(probe: ProviderProbe) -> dict:
    summary = asdict(probe)
    summary["chain_id_gate"] = chain_identity_gate(probe)
    return summary

def _default_urls(cli_urls: List[str]) -> List[str]:
    urls = list(cli_urls)
    for env in ("RH_RPC_PRIMARY", "RH_RPC_SECONDARY"):
        val = os.environ.get(env)
        if val and val not in urls:
            urls.append(val)
    return urls

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an RH_CAPABILITY_MATRIX.json (read-only).")
    parser.add_argument("--rpc-url", action="append", default=[],
                        help="provider endpoint (repeatable)")
    parser.add_argument("--offline-fixture",
                        help="local JSON fixture to replay (no network)")
    parser.add_argument("--out", help="output JSON path")
    args = parser.parse_args(argv)

    urls = _default_urls(args.rpc_url)
    protocol_flags: Dict[str, object] = {"v4_state_view_address": None}
    notes: List[str] = []

    if args.offline_fixture:
        with open(args.offline_fixture, "r", encoding="utf-8") as handle:
            fixture = json.load(handle)
        rpc = _fixture_rpc(fixture)
        probe_urls = urls if urls else ["offline-fixture"]
        probes = [probe_provider(u, rpc=rpc) for u in probe_urls]
        notes.append("OFFLINE_FIXTURE")
    elif urls:
        probes = [probe_provider(u) for u in urls]
    else:
        probes = []
        notes.append("NO_PROVIDER_CONFIGURED")

    matrix = build_capability_matrix(probes, protocol_flags)
    output = {
        "generated_by": "lp_rh_capabilities_v1_readonly",
        "chain_id": RH_CHAIN_ID,
        "probes": [_probe_summary(p) for p in probes],
        "independence": provider_independence(probes),
        "matrix": matrix,
        "notes": notes,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
            handle.write("\n")
    else:
        print(json.dumps(output, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
