"""Tests for scripts/lp_rh_chain_manifest_v1_readonly.py (F1)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from scripts.lp_rh_chain_manifest_v1_readonly import (
    CHAIN_ID_RH_MAINNET,
    CHAIN_ID_RH_TESTNET,
    RH_CORE_TARGETS,
    RH_CORE_SELECTORS,
    MANIFEST_VERIFIED,
    MANIFEST_VERSION,
    MANIFEST_STATUS,
    verify_chain_manifest,
    is_rh_chain,
    _role_is_test,
)


class TestManifestConstants:
    """F1.1 — module constants are correctly defined."""

    def test_chain_id_rh_mainnet(self):
        assert CHAIN_ID_RH_MAINNET == 4663

    def test_chain_id_rh_testnet(self):
        assert CHAIN_ID_RH_TESTNET == 46630

    def test_manifest_version_string(self):
        assert "unverified" in MANIFEST_VERSION.lower()

    def test_manifest_status_unverified_pending_rpc(self):
        assert MANIFEST_STATUS == "UNVERIFIED_PENDING_RPC"

    def test_manifest_verified_false(self):
        assert MANIFEST_VERIFIED is False

    def test_rh_core_targets_is_frozenset(self):
        assert isinstance(RH_CORE_TARGETS, frozenset)
        # All three sentinels resolve to 0x0 so frozenset deduplicates to 1 element.
        # The test validates the structure; real addresses are pending RPC attestation.
        assert len(RH_CORE_TARGETS) >= 1
        assert "0x" + "0" * 40 in RH_CORE_TARGETS

    def test_rh_core_selectors_has_six_selectors(self):
        assert isinstance(RH_CORE_SELECTORS, frozenset)
        assert len(RH_CORE_SELECTORS) == 6
        for sel in ("0x88316456", "0x42966c68", "0xfc6f7865",
                    "0xac9650d8", "0x219f5d17", "0x0c49ccbe"):
            assert sel in RH_CORE_SELECTORS, f"missing selector {sel}"


class TestIsRhChain:
    """F1.2 — is_rh_chain helper."""

    def test_rh_mainnet_true(self):
        assert is_rh_chain(4663) is True

    def test_rh_testnet_true(self):
        assert is_rh_chain(46630) is True

    def test_base_8453_false(self):
        assert is_rh_chain(8453) is False

    def test_other_chain_false(self):
        assert is_rh_chain(1) is False
        assert is_rh_chain(42161) is False


class TestRoleIsTest:
    """F1.3 — _role_is_test helper."""

    def test_test_role_true(self):
        assert _role_is_test("test") is True

    def test_prod_role_false(self):
        assert _role_is_test("prod") is False
        assert _role_is_test("gate") is False
        assert _role_is_test("") is False


class TestVerifyChainManifest:
    """F1.4 — verify_chain_manifest rejects unverified manifest for non-test roles."""

    def test_prod_role_rejected_when_manifest_unverified(self):
        """role=prod + MANIFEST_VERIFIED=False → manifest_reject:unverified_manifest_pending_rpc"""
        ok, reason = verify_chain_manifest(
            chain_id=CHAIN_ID_RH_MAINNET,
            target="0x" + "0" * 40,
            selector="0x88316456",
            role="prod",
        )
        assert ok is False
        assert "unverified_manifest" in reason

    def test_gate_role_rejected_when_manifest_unverified(self):
        """role=gate + MANIFEST_VERIFIED=False → manifest_reject:unverified_manifest_pending_rpc"""
        ok, reason = verify_chain_manifest(
            chain_id=CHAIN_ID_RH_MAINNET,
            target="0x" + "0" * 40,
            selector="0x88316456",
            role="gate",
        )
        assert ok is False
        assert "unverified_manifest" in reason

    def test_test_role_passes_without_verification(self):
        """role=test bypasses the unverified gate."""
        ok, reason = verify_chain_manifest(
            chain_id=CHAIN_ID_RH_MAINNET,
            target="0x" + "0" * 40,
            selector="0x88316456",
            role="test",
        )
        assert ok is True
        assert reason is None

    def test_unsupported_chain_rejected(self):
        """chain_id not in {4663, 46630} → manifest_reject:unsupported_chain:X"""
        ok, reason = verify_chain_manifest(
            chain_id=8453,
            target="0x" + "0" * 40,
            selector="0x88316456",
            role="test",
        )
        assert ok is False
        assert "unsupported_chain" in reason

    def test_unknown_selector_rejected(self):
        """selector not in RH_CORE_SELECTORS → manifest_reject:selector_not_in_rh_core_selectors"""
        ok, reason = verify_chain_manifest(
            chain_id=CHAIN_ID_RH_MAINNET,
            target="0x" + "0" * 40,
            selector="0xdeadbeef",
            role="test",
        )
        assert ok is False
        assert "selector_not_in_rh_core_selectors" in reason

    def test_unknown_target_rejected(self):
        """target not in RH_CORE_TARGETS → manifest_reject:target_not_in_rh_core_targets"""
        ok, reason = verify_chain_manifest(
            chain_id=CHAIN_ID_RH_MAINNET,
            target="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            selector="0x88316456",
            role="test",
        )
        assert ok is False
        assert "target_not_in_rh_core_targets" in reason

    def test_all_six_selectors_accepted_for_test_role(self):
        """All six RH_CORE_SELECTORS pass for test role with sentinel target."""
        target = "0x" + "0" * 40
        for sel in RH_CORE_SELECTORS:
            ok, reason = verify_chain_manifest(
                chain_id=CHAIN_ID_RH_MAINNET,
                target=target,
                selector=sel,
                role="test",
            )
            assert ok is True, f"selector {sel} should pass for test role: {reason}"
