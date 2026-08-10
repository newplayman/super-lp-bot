from __future__ import annotations

from collections import Counter

from scripts.lp_multicall3_v1_readonly import (
    AGGREGATE3_SELECTOR,
    MULTICALL3_ADDRESS,
    BatchedRpcReader,
    Call3,
    Multicall3Reader,
    decode_aggregate3_result,
    encode_aggregate3,
)
from scripts.lp_pool_resolve_and_rank_v1_readonly import (
    SELECTOR_TOKEN0,
    SELECTOR_TOKEN1,
    UNISWAP_V3_FACTORY,
    _read_pool_token_order_and_decimals,
    build_uniswap_get_pool_calldata,
    prime_resolution_reads,
    resolve_pool_with_provenance,
)
from scripts.lp_scanner_daemon_v1_readonly import DefaultStages


def _word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _dynamic(value: bytes) -> bytes:
    return _word(len(value)) + value + b"\x00" * ((-len(value)) % 32)


def _encode_results(items: list[tuple[bool, str]]) -> str:
    blobs = []
    for success, value in items:
        raw = bytes.fromhex(value[2:])
        blobs.append(_word(int(success)) + _word(64) + _dynamic(raw))
    offset = 32 * len(blobs)
    heads = []
    for blob in blobs:
        heads.append(_word(offset))
        offset += len(blob)
    return "0x" + (_word(32) + _word(len(blobs)) + b"".join(heads + blobs)).hex()


def _decode_calls(value: str) -> list[tuple[str, str, bool]]:
    assert value.startswith(AGGREGATE3_SELECTOR)
    raw = bytes.fromhex(value[2 + len(AGGREGATE3_SELECTOR) - 2 :])
    array_base = int.from_bytes(raw[0:32], "big")
    count = int.from_bytes(raw[array_base : array_base + 32], "big")
    heads = array_base + 32
    result = []
    for index in range(count):
        relative = int.from_bytes(raw[heads + index * 32 : heads + (index + 1) * 32], "big")
        item = heads + relative
        target = "0x" + raw[item + 12 : item + 32].hex()
        allowed = bool(int.from_bytes(raw[item + 32 : item + 64], "big"))
        data_offset = int.from_bytes(raw[item + 64 : item + 96], "big")
        data_at = item + data_offset
        size = int.from_bytes(raw[data_at : data_at + 32], "big")
        data = "0x" + raw[data_at + 32 : data_at + 32 + size].hex()
        result.append((target, data, allowed))
    return result


class ContractPool:
    def __init__(self, responses: dict[tuple[str, str], str], *, code: str = "0x6000"):
        self.responses = {(to.lower(), data.lower()): value for (to, data), value in responses.items()}
        self.code = code
        self.methods = Counter()

    def call(self, method, params, timeout=20):
        self.methods[method] += 1
        if method == "eth_getCode":
            return self.code
        assert method == "eth_call"
        to = params[0]["to"].lower()
        data = params[0]["data"].lower()
        if to == MULTICALL3_ADDRESS:
            results = []
            for target, payload, allowed in _decode_calls(data):
                assert allowed is True
                key = (target.lower(), payload.lower())
                results.append((key in self.responses, self.responses.get(key, "0x")))
            return _encode_results(results)
        return self.responses[(to, data)]


def _address_word(address: str) -> str:
    return "0x" + "00" * 12 + address[2:].lower()


def test_aggregate3_codec_round_trip_preserves_individual_failure() -> None:
    calls = [
        Call3("0x" + "11" * 20, "0x313ce567"),
        Call3("0x" + "22" * 20, "0xdeadbeef"),
    ]
    encoded = encode_aggregate3(calls)
    assert _decode_calls(encoded) == [
        (calls[0].target, calls[0].call_data, True),
        (calls[1].target, calls[1].call_data, True),
    ]
    returned = _encode_results([(True, "0x" + "00" * 31 + "06"), (False, "0x08c379a0")])
    assert decode_aggregate3_result(returned) == [
        (True, "0x" + "00" * 31 + "06"),
        (False, "0x08c379a0"),
    ]


def test_default_batch_limit_is_60_and_one_failure_does_not_swallow_batch() -> None:
    targets = ["0x" + format(index + 1, "040x") for index in range(61)]
    responses = {
        (target, "0x313ce567"): "0x" + format(index, "064x")
        for index, target in enumerate(targets)
        if index != 17
    }
    pool = ContractPool(responses)
    reader = Multicall3Reader(pool)
    results = reader.execute(Call3(target, "0x313ce567") for target in targets)

    assert reader.batch_size == 60
    assert len(results) == 61
    assert results[16].success is True
    assert results[17].success is False
    assert results[18].success is True
    assert reader.request_counts() == {
        "logical_calls": 61,
        "eth_getCode_requests": 1,
        "aggregate3_requests": 2,
        "serial_fallback_requests": 0,
        "per_call_failures": 1,
    }


def test_failed_runtime_code_check_records_explicit_serial_fallback() -> None:
    target = "0x" + "11" * 20
    pool = ContractPool({(target, "0x313ce567"): "0x" + "00" * 31 + "12"}, code="0x")
    reader = Multicall3Reader(pool)
    [result] = reader.execute([Call3(target, "0x313ce567")])

    assert result.success is True
    assert result.source == "serial_fallback"
    assert "validation_failed" in (result.error or "")
    assert reader.evidence["validation_status"] == "FALLBACK_SERIAL"
    assert reader.evidence["validation_error"]
    assert reader.request_counts()["serial_fallback_requests"] == 1


def test_failed_refresh_cannot_reuse_previous_cycle_latest_cache() -> None:
    target = "0x" + "11" * 20
    key = (target.lower(), "0x313ce567")
    pool = ContractPool({key: "0x" + "00" * 31 + "12"})
    proxy = BatchedRpcReader(pool, Multicall3Reader(pool))
    call = Call3(target, "0x313ce567")
    assert proxy.prime([call])[0].success is True
    assert proxy.cached(target, call.call_data) is not None

    del pool.responses[key]
    assert proxy.prime([call])[0].success is False
    assert proxy.cached(target, call.call_data) is None


def test_resolver_multicall_and_serial_paths_are_field_exact_with_fewer_requests() -> None:
    token0 = "0x" + "11" * 20
    token1 = "0x" + "22" * 20
    pools = ["0x" + "aa" * 20, "0x" + "bb" * 20]
    candidates = [
        {
            "project": "uniswap-v3",
            "underlyingTokens": [token0, token1],
            "fee_tier": fee,
        }
        for fee in (0.0005, 0.003)
    ]
    responses = {
        (UNISWAP_V3_FACTORY, build_uniswap_get_pool_calldata(token0, token1, 500)): _address_word(pools[0]),
        (UNISWAP_V3_FACTORY, build_uniswap_get_pool_calldata(token1, token0, 500)): _address_word(pools[0]),
        (UNISWAP_V3_FACTORY, build_uniswap_get_pool_calldata(token0, token1, 3000)): _address_word(pools[1]),
        (UNISWAP_V3_FACTORY, build_uniswap_get_pool_calldata(token1, token0, 3000)): _address_word(pools[1]),
        (token0, "0x313ce567"): "0x" + format(18, "064x"),
        (token1, "0x313ce567"): "0x" + format(6, "064x"),
    }
    for pool in pools:
        responses[(pool, SELECTOR_TOKEN0)] = _address_word(token0)
        responses[(pool, SELECTOR_TOKEN1)] = _address_word(token1)
        responses[(pool, "0xd0c93a7c")] = "0x" + format(10, "064x")

    def snapshots(rpc):
        pool_cache, decimal_cache = {}, {}
        rows = []
        for candidate in candidates:
            fee = int(round(candidate["fee_tier"] * 1_000_000))
            resolution = resolve_pool_with_provenance(
                rpc,
                candidate["project"],
                token0,
                token1,
                fee,
                pool_cache,
            )
            order = _read_pool_token_order_and_decimals(
                rpc, resolution["pool"], decimal_cache
            )
            rows.append({
                "pool": resolution["pool"],
                "factory": resolution["factory"],
                "token0": order[0],
                "token1": order[1],
                "dec0": order[2],
                "dec1": order[3],
            })
        return rows

    serial_pool = ContractPool(responses)
    serial_rows = snapshots(serial_pool.call)
    serial_contract_calls = serial_pool.methods["eth_call"]

    batch_pool = ContractPool(responses)
    reader = Multicall3Reader(batch_pool)
    proxy = BatchedRpcReader(batch_pool, reader)
    primed = prime_resolution_reads(candidates, proxy)
    batch_rows = snapshots(proxy.call)

    assert batch_rows == serial_rows
    assert primed["logical_calls"] == 12
    assert proxy.cache_hits == 8
    assert reader.request_counts()["aggregate3_requests"] == 3
    assert batch_pool.methods["eth_call"] == 3
    assert batch_pool.methods["eth_call"] < serial_contract_calls


def test_scanner_live_state_batch_is_field_exact_and_one_bad_pool_isolated() -> None:
    pools = ["0x" + "aa" * 20, "0x" + "bb" * 20]
    responses = {
        (pools[0], "0x3850c7bd"): "0x" + format(123456, "064x") + "00" * 32,
        (pools[0], "0x1a686502"): "0x" + format(654321, "064x"),
        # A failed slot0 must not discard the other pool's successful state.
        (pools[1], "0x1a686502"): "0x" + format(777, "064x"),
    }
    pool = ContractPool(responses)
    stages = DefaultStages(rpc_pool=pool)
    rows = stages._attach_live_pool_states([
        {"pool": pools[0]},
        {"pool": pools[1]},
    ])

    assert rows[0]["sqrt_price_x96"] == 123456
    assert rows[0]["l_active_raw"] == 654321
    assert "sqrt_price_x96" not in rows[1]
    assert rows[1]["l_active_raw"] == 777
    assert stages.multicall3_evidence["request_counts"]["aggregate3_requests"] == 1
    assert stages.multicall3_evidence["request_counts"]["per_call_failures"] == 1
    assert stages.multicall3_evidence["cache_hits"] == 3
    # Failed prime was retried singly and stayed fail-closed without affecting
    # either successful field.
    assert stages.multicall3_evidence["failed_primes"] == 1
