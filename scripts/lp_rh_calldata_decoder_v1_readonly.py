import sys
sys.path.insert(0, "/opt/lpbot/lp-bot-v3-origin-check")
import argparse
import json
import time
from collections.abc import Mapping
def _layout(method, names, types):
    return {"method": method, "names": tuple(names), "types": tuple(types)}
SELECTORS = {
    "0x095ea7b3": _layout("approve", ("spender", "amount"), ("address", "uint256")),
    "0xa9059cbb": _layout("transfer", ("recipient", "amount"), ("address", "uint256")),
    "0x04e45aaf": _layout("exactInputSingle",
        ("tokenIn", "tokenOut", "fee", "recipient", "deadline", "amountIn", "amountOutMinimum", "sqrtPriceLimitX96"),
        ("address", "address", "uint24", "address", "uint256", "uint256", "uint256", "uint160")),
    "0x88316456": _layout("mint",
        ("token0", "token1", "fee", "tickLower", "tickUpper", "amount0Desired", "amount1Desired", "amount0Min", "amount1Min", "recipient", "deadline"),
        ("address", "address", "uint24", "int24", "int24", "uint256", "uint256", "uint256", "uint256", "address", "uint256")),
    "0x219f5d17": _layout("increaseLiquidity",
        ("tokenId", "amount0Desired", "amount1Desired", "amount0Min", "amount1Min", "deadline"),
        ("uint256", "uint256", "uint256", "uint256", "uint256", "uint256")),
    "0x0c49ccbe": _layout("decreaseLiquidity",
        ("tokenId", "liquidity", "amount0Min", "amount1Min", "deadline"),
        ("uint256", "uint128", "uint256", "uint256", "uint256")),
    "0xfc6f7865": _layout("collect", ("tokenId", "recipient", "amount0Max", "amount1Max"), ("uint256", "address", "uint128", "uint128")),
    "0x42966c68": _layout("burn", ("tokenId",), ("uint256",)),
    "0xac9650d8": _layout("multicall", ("calls",), ("bytes[]",)),
}
# No guessed selector is placed here. Unrecognised values are added at runtime.
UNKNOWN_SELECTORS = set()
def _result(selector, known, args, raw_words, status):
    return {"selector": selector, "known": known, "args": args,
            "raw_words": raw_words, "status": status}
def _arg(name, typ, value):
    return {"name": name, "type": typ, "value": value}
def _uint(word):
    return int.from_bytes(word, "big")
def _value(word, typ):
    number = _uint(word)
    if typ == "address":
        return "0x" + word[-20:].hex()
    if typ.startswith("int"):
        bits = int(typ[3:])
        number &= (1 << bits) - 1
        if number >= 1 << (bits - 1):
            number -= 1 << bits
    return number
def _hex_bytes(data):
    if not isinstance(data, str):
        raise ValueError("not text")
    text = data[2:] if data.lower().startswith("0x") else data
    if len(text) < 8 or len(text) % 2:
        raise ValueError("short or odd hex")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError("bad hex") from exc
def _word_at(data, offset):
    if offset < 0 or offset + 32 > len(data):
        raise ValueError("word out of bounds")
    return data[offset:offset + 32]
def _decode_bytes_array(body):
    top = _uint(_word_at(body, 0))
    if top % 32 or top < 32:
        raise ValueError("bad array offset")
    count = _uint(_word_at(body, top))
    head = top + 32
    if head + count * 32 > len(body):
        raise ValueError("short array head")
    children = []
    for index in range(count):
        relative = _uint(_word_at(body, head + index * 32))
        start = top + relative
        if start < head or start % 32:
            raise ValueError("bad item offset")
        length = _uint(_word_at(body, start))
        data_start = start + 32
        data_end = data_start + length
        padded_end = data_start + ((length + 31) // 32) * 32
        if data_end > len(body) or padded_end > len(body):
            raise ValueError("short item")
        children.append(decode_calldata("0x" + body[data_start:data_end].hex()))
    return [_arg("calls", "bytes[]", children)]
def decode_calldata(data: str) -> dict:
    """Decode known ABI words without network or chain dependencies."""
    try:
        raw = _hex_bytes(data)
    except ValueError:
        return _result("", False, [], 0, "MALFORMED_CALLDATA")
    selector = "0x" + raw[:4].hex()
    body = raw[4:]
    raw_words = len(body) // 32
    if len(raw) < 4 or len(body) % 32:
        return _result(selector, selector in SELECTORS, [], raw_words, "MALFORMED_CALLDATA")
    layout = SELECTORS.get(selector)
    if layout is None:
        UNKNOWN_SELECTORS.add(selector)
        return _result(selector, False, [], raw_words, "UNKNOWN_SELECTOR")
    try:
        if layout["method"] == "multicall":
            args = _decode_bytes_array(body)
            statuses = [x.get("status") for x in args[0]["value"] if x.get("status") != "OK"]
            status = "MALFORMED_CALLDATA" if "MALFORMED_CALLDATA" in statuses else "OK"
            if status == "OK" and statuses:
                status = "UNKNOWN_SELECTOR"
            return _result(selector, True, args, raw_words, status)
        types = layout["types"]
        if len(body) < len(types) * 32:
            raise ValueError("short arguments")
        args = [_arg(name, typ, _value(body[i * 32:(i + 1) * 32], typ))
                for i, (name, typ) in enumerate(zip(layout["names"], types))]
        if layout["method"] == "collect" and raw_words > len(types):
            args.extend(_arg("fabricated_min_out_%d" % (i - len(types)), "uint256",
                             _uint(body[i * 32:(i + 1) * 32]))
                        for i in range(len(types), raw_words))
        return _result(selector, True, args, raw_words, "OK")
    except (ValueError, IndexError):
        return _result(selector, True, [], raw_words, "MALFORMED_CALLDATA")
def _norm(value):
    return value.lower() if isinstance(value, str) else ""
def _method(call):
    layout = SELECTORS.get(_norm(call.get("selector", "")))
    return call.get("method") or (layout["method"] if layout else "")
def _args(call):
    value = call.get("args", [])
    return value if isinstance(value, list) else []
def _children(call):
    children = []
    for item in _args(call):
        if isinstance(item, Mapping) and item.get("name") == "calls":
            values = item.get("value", [])
            if isinstance(values, list):
                children.extend((i, x) for i, x in enumerate(values) if isinstance(x, Mapping))
    extra = call.get("subcalls", [])
    if isinstance(extra, list):
        children.extend((i, x) for i, x in enumerate(extra) if isinstance(x, Mapping))
    return children
def _walk(call, path="root"):
    yield call, path
    for index, child in _children(call):
        yield from _walk(child, "%s.subcall[%d]" % (path, index))
def _self_wallets(decoded):
    wallets = set()
    for call, _ in _walk(decoded):
        sources = [call]
        sources.extend(x for x in (call.get("metadata"), call.get("intent")) if isinstance(x, Mapping))
        for source in sources:
            for key in ("self_wallet", "wallet_address", "wallet_id", "wallet"):
                value = source.get(key)
                if isinstance(value, str) and len(value) == 42 and value[:2].lower() == "0x":
                    wallets.add(value.lower())
    return wallets
def check_targets(decoded, *, target, allowlist: set[str]) -> tuple[bool, list[str]]:
    allowed = {_norm(item) for item in allowlist}
    reasons = []
    if _norm(target) not in allowed:
        reasons.append("TARGET_NOT_ALLOWLISTED")
    recipients = allowed | _self_wallets(decoded)
    for call, path in _walk(decoded):
        explicit = call.get("target", call.get("call_target"))
        if explicit is not None and _norm(explicit) not in allowed:
            reasons.append("SUBCALL_TARGET_NOT_ALLOWLISTED:" + path)
        for item in _args(call):
            if isinstance(item, Mapping) and item.get("name") == "recipient" and _norm(item.get("value")) not in recipients:
                reasons.append("RECIPIENT_NOT_ALLOWLISTED:%s.recipient" % path)
    return not reasons, reasons
def _int_value(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None
def check_amount_protection(decoded, *, leg0_expected_zero: bool,
                            leg1_expected_zero: bool) -> tuple[bool, list[str]]:
    reasons = []
    for call, path in _walk(decoded):
        method = _method(call)
        for item in _args(call):
            if not isinstance(item, Mapping):
                continue
            name, value = str(item.get("name", "")), _int_value(item.get("value"))
            low = name.lower()
            if method == "collect" and ("min" in low or ("out" in low and "max" not in low)):
                reasons.append("FABRICATED_MIN_OUT_ON_COLLECT:" + path)
                continue
            if name == "amount0Min":
                zero = leg0_expected_zero
            elif name in ("amount1Min", "amountOutMinimum"):
                zero = leg1_expected_zero
            else:
                continue
            if value == 0 and zero:
                reasons.append("LEGITIMATE_ZERO_LEG:%s.%s" % (path, name))
            elif value == 0 and not zero:
                reasons.append("MISSING_SLIPPAGE_PROTECTION:%s.%s" % (path, name))
    bad = [x for x in reasons if not x.startswith("LEGITIMATE_ZERO_LEG")]
    return not bad, reasons
def check_deadline(decoded, *, now_unix: int, max_horizon_secs: int = 300) -> tuple[bool, str]:
    deadlines = []
    for call, _ in _walk(decoded):
        deadlines.extend(_int_value(item.get("value")) for item in _args(call)
                         if isinstance(item, Mapping) and item.get("name") == "deadline")
    deadlines = [x for x in deadlines if x is not None]
    if not deadlines:
        return False, "DEADLINE_MISSING"
    if any(x <= now_unix for x in deadlines):
        return False, "DEADLINE_EXPIRED"
    if any(x > now_unix + max_horizon_secs for x in deadlines):
        return False, "DEADLINE_TOO_FAR"
    return True, "OK"
def check_approval(decoded) -> tuple[bool, str]:
    for call, _ in _walk(decoded):
        if _method(call) == "approve":
            for item in _args(call):
                if isinstance(item, Mapping) and item.get("name") == "amount":
                    value = _int_value(item.get("value"))
                    if value is not None and value >= 2 ** 255:
                        return False, "UNLIMITED_APPROVAL_FORBIDDEN"
    return True, "OK"
_INTENT_FIELDS = ("chain_id", "wallet_id", "position_id", "request_id", "decision_id",
                  "idempotency_key", "policy_hash", "code_version", "snapshot_hash",
                  "calldata_hash", "expires_at")
def _claims(decoded):
    claims = {}
    for key in ("metadata", "claims", "intent"):
        value = decoded.get(key)
        if isinstance(value, Mapping):
            claims.update(value)
    claims.update({k: v for k, v in decoded.items() if k not in ("args", "metadata", "claims", "intent")})
    for item in _args(decoded):
        if isinstance(item, Mapping) and "name" in item:
            claims[item["name"]] = item.get("value")
    claims.setdefault("selector", decoded.get("selector"))
    return claims
def _same(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower() if left.startswith("0x") and right.startswith("0x") else left == right
    left_int, right_int = _int_value(left), _int_value(right)
    return left_int == right_int if left_int is not None and right_int is not None else left == right
def verify_intent(decoded, *, intent: Mapping) -> tuple[bool, list[str]]:
    if not isinstance(intent, Mapping):
        return False, ["INTENT_MISSING"]
    missing = [x for x in _INTENT_FIELDS if x not in intent or intent[x] is None]
    if missing:
        return False, ["INTENT_FIELD_MISSING:" + x for x in missing]
    claims = _claims(decoded)
    missing_claims = [x for x in _INTENT_FIELDS if x not in claims]
    reasons = (["INTENT_CLAIM_MISSING:" + x for x in missing_claims] +
               ["INTENT_MISMATCH:" + x for x in _INTENT_FIELDS
                if x in claims and not _same(claims[x], intent[x])])
    return not reasons, reasons
def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
def main():
    parser = argparse.ArgumentParser(description="Offline calldata decoder")
    for name in ("calldata", "target", "allowlist-json", "intent-json", "out"):
        parser.add_argument("--" + name, required=True)
    options = parser.parse_args()
    allowlist = _read_json(options.allowlist_json)
    if isinstance(allowlist, Mapping):
        allowlist = allowlist.get("allowlist", allowlist.get("addresses", []))
    decoded = decode_calldata(options.calldata)
    target_ok, target_reasons = check_targets(decoded, target=options.target, allowlist=set(allowlist or []))
    amount_ok, amount_reasons = check_amount_protection(decoded, leg0_expected_zero=False, leg1_expected_zero=False)
    deadline_ok, deadline_reason = check_deadline(decoded, now_unix=int(time.time()))
    approval_ok, approval_reason = check_approval(decoded)
    intent_ok, intent_reasons = verify_intent(decoded, intent=_read_json(options.intent_json))
    output = {"decoded": decoded, "targets": {"ok": target_ok, "reasons": target_reasons},
              "amount_protection": {"ok": amount_ok, "reasons": amount_reasons},
              "deadline": {"ok": deadline_ok, "reason": deadline_reason},
              "approval": {"ok": approval_ok, "reason": approval_reason},
              "intent": {"ok": intent_ok, "reasons": intent_reasons}}
    with open(options.out, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, sort_keys=True)
if __name__ == "__main__":
    main()
