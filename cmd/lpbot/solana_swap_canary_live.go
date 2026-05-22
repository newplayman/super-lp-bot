//go:build live

package main

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const solanaCanaryMaxSOLAmountRaw uint64 = 10000000
const solanaCanaryMaxUSDCAmountRaw uint64 = 1000000

func runSolanaSwapCanary(ctx context.Context, cfg *config.Config, userPublicKey string, inputMint string, outputMint string, amountRaw string, slippageBPS int, maxPriorityLamports uint64) error {
	if cfg == nil {
		return fmt.Errorf("config is required")
	}
	inputMint = strings.TrimSpace(inputMint)
	outputMint = strings.TrimSpace(outputMint)
	rawAmount, err := strconv.ParseUint(strings.TrimSpace(amountRaw), 10, 64)
	if err != nil || rawAmount == 0 {
		return fmt.Errorf("invalid solana canary amount raw %q", amountRaw)
	}

	switch {
	case inputMint == solanaWrappedSOLAddress && outputMint == solanaUSDCAddress:
		if rawAmount > solanaCanaryMaxSOLAmountRaw {
			return fmt.Errorf("solana canary %s -> %s max amount is %d raw (0.01 SOL)", solanaWrappedSOLAddress, solanaUSDCAddress, solanaCanaryMaxSOLAmountRaw)
		}
	case inputMint == solanaUSDCAddress && outputMint == solanaWrappedSOLAddress:
		if rawAmount > solanaCanaryMaxUSDCAmountRaw {
			return fmt.Errorf("solana canary %s -> %s max amount is %d raw (1 USDC)", solanaUSDCAddress, solanaWrappedSOLAddress, solanaCanaryMaxUSDCAmountRaw)
		}
	default:
		return fmt.Errorf("solana canary only allows %s <-> %s", solanaWrappedSOLAddress, solanaUSDCAddress)
	}

	quote, built, err := buildJupiterSwapTransaction(ctx, userPublicKey, inputMint, outputMint, amountRaw, slippageBPS, maxPriorityLamports)
	if err != nil {
		return err
	}
	if quote.InAmount != amountRaw {
		return fmt.Errorf("unexpected quote input amount: got %s want %s", quote.InAmount, amountRaw)
	}
	if len(built.SimulationError) > 0 && string(built.SimulationError) != "null" {
		return fmt.Errorf("solana canary blocked by simulation: %s", compactJSON(built.SimulationError))
	}

	key, keySource, ok, err := loadSolanaPrivateKeyFromEnv()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("missing signer env: SOLANA_PRIVATE_KEY|SOLANA_KEYPAIR_JSON|SOLANA_KEYPAIR_PATH")
	}
	pub := key.PublicKey().String()
	if pub != built.UserPublicKey {
		return fmt.Errorf("solana signer public key mismatch: signer=%s user=%s", shortAddress(pub), shortAddress(built.UserPublicKey))
	}

	tx, signedBytes, signature, err := signJupiterSwapTransaction(built.SwapTransaction, key)
	if err != nil {
		return err
	}
	_ = tx

	broadcaster, err := livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:    strings.TrimSpace(cfg.Chains.Base.RPCPrimary),
		SolanaRPCURL:  solanaReadinessEndpoint(cfg),
		Confirmations: cfg.Chains.Base.Confirmations,
	})
	if err != nil {
		return fmt.Errorf("initialize solana live broadcaster: %w", err)
	}

	signedTx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:     "solana-swap-canary",
			Chain:  domain.ChainSolana,
			From:   domain.MustParseAddress(pub),
			To:     domain.MustParseAddress(outputMint),
			MinOut: domain.NewDecimalFromInt(0),
		},
		Signature: signedBytes,
		Hash:      signature,
		Status:    domain.TxBuilt,
	}

	fmt.Printf("solana_swap_canary_prepare source=%s user=%s in_amount=%s out_amount=%s tx_base64_len=%d signed_bytes=%d signature=%s\n",
		keySource,
		shortAddress(pub),
		quote.InAmount,
		quote.OutAmount,
		len(built.SwapTransaction),
		len(signedBytes),
		shortAddress(signature),
	)
	if err := broadcaster.Send(ctx, signedTx); err != nil {
		return fmt.Errorf("broadcast solana canary swap: %w", err)
	}
	fmt.Printf("solana_swap_canary_broadcast success=true signature=%s in_amount=%s out_amount=%s\n", signature, quote.InAmount, quote.OutAmount)
	return nil
}
