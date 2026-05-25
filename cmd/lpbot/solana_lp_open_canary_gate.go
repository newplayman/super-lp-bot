package main

import (
	"fmt"
	"strings"

	solanago "github.com/gagliardetto/solana-go"
	"github.com/lpbot/lpbot/internal/domain"
)

const solanaLPOpenCanaryMaxTotalUSD = 10.0

func validateSolanaLPOpenCanaryPreflight(preflight solanaLPPreflight) error {
	if !preflight.Plan.TargetTotalUSD.LessThanOrEqual(domain.MustDecimal("10")) {
		return fmt.Errorf("solana lp open canary max total usd is %.0f", solanaLPOpenCanaryMaxTotalUSD)
	}
	if preflight.Plan.Status != "ready_direct" {
		return fmt.Errorf("solana lp open canary requires direct funding path; status=%s blocker=%s", preflight.Plan.Status, preflight.Plan.Blocker)
	}
	if !preflight.FundingReady {
		return fmt.Errorf("solana lp open canary funding is not ready")
	}
	if !strings.EqualFold(strings.TrimSpace(preflight.PoolProtocol), "pancakeswap-v3-solana") {
		return fmt.Errorf("solana lp open canary only supports pancakeswap-v3-solana; protocol=%s", preflight.PoolProtocol)
	}
	if strings.TrimSpace(preflight.PoolID) == "" {
		return fmt.Errorf("solana lp open canary pool id is empty")
	}
	if !preflight.LPBuildReady {
		return fmt.Errorf("solana lp build is not ready")
	}
	if !preflight.LPSignReady {
		return fmt.Errorf("solana lp sign is not ready")
	}
	if !preflight.LPSimReady {
		return fmt.Errorf("solana lp simulation is not ready")
	}
	if preflight.LPBuildBase64Len == 0 {
		return fmt.Errorf("solana lp open canary build payload is empty")
	}
	if strings.TrimSpace(preflight.PositionNFTMint) == "" {
		return fmt.Errorf("solana lp open canary position mint is empty")
	}
	if strings.TrimSpace(preflight.LPSignature) == "" {
		return fmt.Errorf("solana lp open canary signature is empty")
	}
	return nil
}

func refreshSolanaTransactionBlockhash(tx *solanago.Transaction, blockhash solanago.Hash) {
	if tx == nil {
		return
	}
	tx.Message.RecentBlockhash = blockhash
	for i := range tx.Signatures {
		tx.Signatures[i] = solanago.Signature{}
	}
}
