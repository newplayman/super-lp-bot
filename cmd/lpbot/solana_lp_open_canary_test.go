package main

import (
	"strings"
	"testing"

	solanago "github.com/gagliardetto/solana-go"
	"github.com/lpbot/lpbot/internal/domain"
)

func TestValidateSolanaLPOpenCanaryPreflight(t *testing.T) {
	for _, tc := range []struct {
		name      string
		preflight solanaLPPreflight
		wantErr   string
	}{
		{
			name: "ready direct simulated path passes",
			preflight: solanaLPPreflight{
				Plan: solanaLPFundingPlan{
					Status:         "ready_direct",
					TargetTotalUSD: domain.MustDecimal("10"),
				},
				FundingReady:      true,
				LPBuildReady:      true,
				LPSignReady:       true,
				LPSimReady:        true,
				PoolID:            solanaKnownSOLUSDCPool,
				PoolProtocol:      "pancakeswap-v3-solana",
				LPBuildBase64Len:  10,
				PositionNFTMint:   "mint",
				LPSignature:       "sig",
			},
		},
		{
			name: "requires prefund is rejected",
			preflight: solanaLPPreflight{
				Plan: solanaLPFundingPlan{
					Status:         "requires_prefund_swap",
					TargetTotalUSD: domain.MustDecimal("10"),
				},
				FundingReady: true,
			},
			wantErr: "requires direct funding path",
		},
		{
			name: "oversized total usd is rejected",
			preflight: solanaLPPreflight{
				Plan: solanaLPFundingPlan{
					Status:         "ready_direct",
					TargetTotalUSD: domain.MustDecimal("11"),
				},
				FundingReady: true,
			},
			wantErr: "max total usd",
		},
		{
			name: "simulation gate is required",
			preflight: solanaLPPreflight{
				Plan: solanaLPFundingPlan{
					Status:         "ready_direct",
					TargetTotalUSD: domain.MustDecimal("10"),
				},
				FundingReady: true,
				LPBuildReady: true,
				LPSignReady:  true,
				PoolID:       solanaKnownSOLUSDCPool,
				PoolProtocol: "pancakeswap-v3-solana",
			},
			wantErr: "lp simulation is not ready",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := validateSolanaLPOpenCanaryPreflight(tc.preflight)
			if tc.wantErr == "" && err != nil {
				t.Fatalf("expected success, got error: %v", err)
			}
			if tc.wantErr != "" {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil", tc.wantErr)
				}
				if !strings.Contains(err.Error(), tc.wantErr) {
					t.Fatalf("expected error containing %q, got %q", tc.wantErr, err.Error())
				}
			}
		})
	}
}

func TestRefreshSolanaTransactionBlockhash(t *testing.T) {
	oldHash := solanago.MustHashFromBase58("11111111111111111111111111111112")
	newHash := solanago.MustHashFromBase58("11111111111111111111111111111113")
	tx := &solanago.Transaction{
		Signatures: []solanago.Signature{
			solanago.Signature{1},
			solanago.Signature{2},
		},
		Message: solanago.Message{
			RecentBlockhash: oldHash,
		},
	}

	refreshSolanaTransactionBlockhash(tx, newHash)

	if !tx.Message.RecentBlockhash.Equals(newHash) {
		t.Fatalf("expected blockhash %s, got %s", newHash.String(), tx.Message.RecentBlockhash.String())
	}
	for i, sig := range tx.Signatures {
		if !sig.IsZero() {
			t.Fatalf("expected signature %d to be zeroed", i)
		}
	}
}
