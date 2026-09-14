"""
RH Chain Manifest V1 — readonly manifest for RH (chain_id=4663) target/selector binding.

No RPC calls. No live signing. No chain access.
MANIFEST_VERIFIED=False until external attestation via RPC.

This module is the single source of truth for RH-core onchain target+selector bindings.
Role "test" bypasses the unverified gate for local fixture testing only.
"""

CHAIN_ID_RH_MAINNET = 4663
CHAIN_ID_RH_TESTNET = 46630

# Uniswap V3 NPM address on RH mainnet — 0x0 sentinel until RPC attestation.
# Marked UNVERIFIED; do not promote to VERIFIED without RPC confirmation.
_NPM_RH_MAINNET_SENTINEL = "0x0000000000000000000000000000000000000000"
_FACTORY_RH_MAINNET_SENTINEL = "0x0000000000000000000000000000000000000000"
_NPM_RH_TESTNET_SENTINEL = "0x0000000000000000000000000000000000000000"

# RH_CORE_TARGETS — frozenset of whitelisted onchain contract addresses.
# All entries use 0x0 sentinel until RPC attestation is performed.
RH_CORE_TARGETS: frozenset[str] = frozenset([
    _NPM_RH_MAINNET_SENTINEL,
    _FACTORY_RH_MAINNET_SENTINEL,
    _NPM_RH_TESTNET_SENTINEL,
])

# RH_CORE_SELECTORS — frozenset of permitted function selectors for RH chain.
# selector -> human name (for audit trail only, not used in gate logic)
RH_CORE_SELECTORS: frozenset[str] = frozenset([
    "0x88316456",  # mint
    "0x42966c68",  # burn
    "0xfc6f7865",  # collect
    "0xac9650d8",  # multicall
    "0x219f5d17",  # increaseLiquidity
    "0x0c49ccbe",  # decreaseLiquidity
])

MANIFEST_VERIFIED: bool = False
MANIFEST_VERSION: str = "rh-core-v1.0.0-unverified-2026-09-13"
MANIFEST_STATUS: str = "UNVERIFIED_PENDING_RPC"

# Whitelisted recipient addresses for RH chain.
# Reuses Base set (zero + dead) and adds a test-role sentinel so fixtures
# can use ephemeral addresses.  In production the manifest must be updated
# with real approved recipient addresses.
RH_CORE_RECIPIENTS: frozenset[str] = frozenset([
    "0x0000000000000000000000000000000000000000",  # zero / burn address
    "0x000000000000000000000000000000000000dead",  # project wallet placeholder
    "0x0000000000000000000000000000000000000001",  # test sentinel
    "0xc3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3",  # DUMMY_RECIPIENT test fixture
])


def _role_is_test(role: str) -> bool:
    """Return True only for explicit test-role callers."""
    return role == "test"


def verify_chain_manifest(
    chain_id: int,
    target: str,
    selector: str,
    role: str,
) -> tuple[bool, str | None]:
    """
    Verify that (chain_id, target, selector, role) is a registered combination
    in the RH manifest.

    Args:
        chain_id: The chain ID to validate against.
        target:   The onchain contract address (checksummed or not — we normalise).
        selector: The function selector (4-byte hex string, e.g. "0x88316456").
        role:     The caller role. "test" bypasses the unverified gate for fixture use.
                  Any other role is treated as production.

    Returns:
        (True, None)  — the combination is registered and permitted.
        (False, "manifest_reject:<reason>") — the combination is not registered.

    Rules:
    1. If MANIFEST_VERIFIED is False and role != "test", reject immediately.
       (This is the RH-specific gate: we must not admit real positions on
        unverified target/selector bindings.)
    2. chain_id must be RH_MAINNET (4663) or RH_TESTNET (46630).
    3. target must be in RH_CORE_TARGETS.
    4. selector must be in RH_CORE_SELECTORS.
    """
    # Rule 1 — unverified manifest gate
    if not MANIFEST_VERIFIED and not _role_is_test(role):
        return (False, "manifest_reject:unverified_manifest_pending_rpc")

    # Rule 2 — chain_id gate
    if chain_id not in (CHAIN_ID_RH_MAINNET, CHAIN_ID_RH_TESTNET):
        return (False, f"manifest_reject:unsupported_chain:{chain_id}")

    # Rule 3 — target must be whitelisted
    # Normalise to lowercase for comparison (all targets stored as 0x-prefixed hex)
    target_lower = target.lower() if isinstance(target, str) else ""
    if target_lower not in RH_CORE_TARGETS:
        return (False, "manifest_reject:target_not_in_rh_core_targets")

    # Rule 4 — selector must be whitelisted
    selector_normalised = selector.lower() if isinstance(selector, str) else ""
    if selector_normalised not in RH_CORE_SELECTORS:
        return (False, "manifest_reject:selector_not_in_rh_core_selectors")

    # All checks passed
    return (True, None)


# Convenience predicate used by gate wrappers
def is_rh_chain(chain_id: int) -> bool:
    return chain_id in (CHAIN_ID_RH_MAINNET, CHAIN_ID_RH_TESTNET)


if __name__ == "__main__":
    # Self-test (no pytest needed for basic sanity)
    ok, reason = verify_chain_manifest(
        chain_id=CHAIN_ID_RH_MAINNET,
        target=_NPM_RH_MAINNET_SENTINEL,
        selector="0x88316456",
        role="test",
    )
    print(f"[self-test] role=test  -> ok={ok}, reason={reason}")
    assert ok is True, f"self-test failed: {reason}"

    ok2, reason2 = verify_chain_manifest(
        chain_id=CHAIN_ID_RH_MAINNET,
        target=_NPM_RH_MAINNET_SENTINEL,
        selector="0x88316456",
        role="prod",
    )
    print(f"[self-test] role=prod -> ok={ok2}, reason={reason2}")
    assert ok2 is False, "prod role should be rejected when MANIFEST_VERIFIED=False"
    assert "unverified_manifest" in reason2

    print("[self-test] ALL PASS")
