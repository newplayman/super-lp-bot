//go:build live

package main

import (
	"context"
	"errors"
	"fmt"
	"time"

	solrpc "github.com/gagliardetto/solana-go/rpc"
	solanago "github.com/gagliardetto/solana-go"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaLPOpenCanary(ctx context.Context, cfg *config.Config, userPublicKey string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) error {
	if cfg == nil {
		return fmt.Errorf("config is required")
	}
	quotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaSOLUSDCLPFundingPlan(ctx, cfg, userPublicKey, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
	if err != nil {
		return err
	}
	printSolanaLPFundingPlan(plan)

	preflight := solanaLPPreflight{
		Plan:             plan,
		FundingReady:     plan.Status == "ready_direct",
		PostPrefundBalanceReady: plan.Status == "ready_direct",
		PostPrefundSOLRaw:  plan.SOLBalanceRaw,
		PostPrefundUSDCRaw: plan.USDCBalanceRaw,
		PoolID:           solanaKnownSOLUSDCPool,
		PoolProtocol:     "pancakeswap-v3-solana",
		PreferredPoolID:  solanaKnownSOLUSDCPool,
		PreferredProtocol:"pancakeswap-v3-solana",
	}

	openBuild, err := buildPancakeSolanaOpenPositionTransaction(ctx, cfg, preflight.PoolID, plan)
	if err != nil {
		return fmt.Errorf("solana lp open canary build failed: %w", err)
	}
	preflight.LPBuildReady = true
	preflight.LPBuildBase64Len = len(openBuild.TxBase64)
	preflight.PositionNFTMint = openBuild.PositionNFT.PublicKey().String()
	preflight.RangeSummary, preflight.FeeProjection, preflight.ExitSignal = computeSolanaLPAnalytics(ctx, preflight.PoolID, preflight.PoolProtocol, nil, openBuild.PoolState, openBuild.TickLower, openBuild.TickUpper, plan.TargetTotalUSD, maxPriorityLamports)
	fmt.Printf("solana_lp_open_canary_build ready=true pool_id=%s protocol=%s amount0_max=%d amount1_max=%d wrap_sol_required=%t tx_base64_len=%d nft_mint=%s\n",
		preflight.PoolID,
		preflight.PoolProtocol,
		openBuild.Amount0Max,
		openBuild.Amount1Max,
		openBuild.WrapSOLRequired,
		len(openBuild.TxBase64),
		shortAddress(preflight.PositionNFTMint),
	)

	key, keySource, ok, err := loadSolanaPrivateKeyFromEnv()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("missing signer env: SOLANA_PRIVATE_KEY|SOLANA_KEYPAIR_JSON|SOLANA_KEYPAIR_PATH")
	}
	signature, err := signPancakeSolanaOpenPositionTransaction(openBuild.Tx, key, openBuild.PositionNFT)
	if err != nil {
		return err
	}
	preflight.LPSignReady = true
	preflight.LPSignature = signature
	fmt.Printf("solana_lp_open_canary_sign ready=true source=%s signature=%s nft_mint=%s\n",
		keySource,
		shortAddress(signature),
		shortAddress(preflight.PositionNFTMint),
	)

	if err := simulateSignedSolanaOpenPosition(ctx, cfg, openBuild); err != nil {
		return err
	}
	preflight.LPSimReady = true

	if err := validateSolanaLPOpenCanaryPreflight(preflight); err != nil {
		return err
	}

	client := solrpc.New(solanaReadinessEndpoint(cfg))
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentProcessed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return fmt.Errorf("refresh solana lp open canary blockhash: %w", err)
	}
	refreshSolanaTransactionBlockhash(openBuild.Tx, blockhashResp.Value.Blockhash)
	signature, err = signPancakeSolanaOpenPositionTransaction(openBuild.Tx, key, openBuild.PositionNFT)
	if err != nil {
		return fmt.Errorf("re-sign solana lp open canary with fresh blockhash: %w", err)
	}
	preflight.LPSignature = signature

	signedBytes, err := openBuild.Tx.MarshalBinary()
	if err != nil {
		return fmt.Errorf("marshal signed solana lp open transaction: %w", err)
	}

	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()

	pub := key.PublicKey().String()

	signedTx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:     "solana-lp-open-canary-" + signature,
			Chain:  domain.ChainSolana,
			From:   domain.MustParseAddress(pub),
			To:     domain.MustParseAddress(preflight.PoolID),
			MinOut: domain.ZeroDecimal(),
		},
		Signature: signedBytes,
		Hash:      signature,
		Status:    domain.TxBuilt,
	}

	if err := state.Record(ctx, canaryEvent{
		Chain:           domain.ChainSolana.String(),
		Command:         "solana_lp_open_canary",
		Stage:           "signed",
		Status:          "ok",
		Wallet:          pub,
		TxHash:          signature,
		InputMint:       plan.Token0,
		OutputMint:      plan.Token1,
		InputAmountRaw:  fmt.Sprintf("%d", plan.TargetToken0Raw),
		OutputAmountRaw: fmt.Sprintf("%d", plan.TargetToken1Raw),
		Message:         fmt.Sprintf("signed LP open pool=%s token0=%d token1=%d", shortAddress(preflight.PoolID), plan.TargetToken0Raw, plan.TargetToken1Raw),
		CreatedAt:       time.Now().Unix(),
	}); err != nil {
		return fmt.Errorf("record solana lp open signed event: %w", err)
	}
	if err := state.RecordSignedTx(ctx, signedTx, domain.TxBuilt); err != nil {
		return fmt.Errorf("record solana lp open built tx: %w", err)
	}

	fmt.Printf("solana_lp_open_canary_prepare source=%s user=%s token0_amount=%d token1_amount=%d signed_bytes=%d signature=%s nft_mint=%s\n",
		keySource,
		shortAddress(pub),
		plan.TargetToken0Raw,
		plan.TargetToken1Raw,
		len(signedBytes),
		shortAddress(signature),
		shortAddress(preflight.PositionNFTMint),
	)

	txSig, err := client.SendTransactionWithOpts(ctx, openBuild.Tx, solrpc.TransactionOpts{
		SkipPreflight:       true,
		PreflightCommitment: solrpc.CommitmentProcessed,
	})
	if err != nil {
		return fmt.Errorf("broadcast solana lp open canary: %w", err)
	}
	if txSig.String() != signature {
		return fmt.Errorf("solana lp open canary signature mismatch after send: built=%s sent=%s", signature, txSig.String())
	}
	if err := waitForDirectSolanaConfirmation(ctx, client, txSig); err != nil {
		return fmt.Errorf("confirm solana lp open canary: %w", err)
	}
	if err := state.RecordSignedTx(ctx, signedTx, domain.TxBroadcast); err != nil {
		return fmt.Errorf("record solana lp open broadcast tx: %w", err)
	}
	if err := state.Record(ctx, canaryEvent{
		Chain:           domain.ChainSolana.String(),
		Command:         "solana_lp_open_canary",
		Stage:           "broadcast",
		Status:          "ok",
		Wallet:          pub,
		TxHash:          signature,
		InputMint:       plan.Token0,
		OutputMint:      plan.Token1,
		InputAmountRaw:  fmt.Sprintf("%d", plan.TargetToken0Raw),
		OutputAmountRaw: fmt.Sprintf("%d", plan.TargetToken1Raw),
		Message:         fmt.Sprintf("broadcast LP open pool=%s", shortAddress(preflight.PoolID)),
		CreatedAt:       time.Now().Unix(),
	}); err != nil {
		return fmt.Errorf("record solana lp open broadcast event: %w", err)
	}
	metadataJSON, err := buildSolanaLPPositionMetadata(preflight.PoolProtocol, preflight.PoolID, openBuild, plan, signature, preflight.RangeSummary, preflight.FeeProjection, preflight.ExitSignal)
	if err != nil {
		return err
	}
	if err := saveConfirmedSolanaOpenPosition(ctx, state.db, preflight.PoolID, preflight.PoolProtocol, openBuild, plan, signature, metadataJSON); err != nil {
		return fmt.Errorf("persist solana lp open position: %w", err)
	}
	fmt.Printf("solana_lp_open_canary_broadcast success=true signature=%s nft_mint=%s\n", signature, shortAddress(preflight.PositionNFTMint))
	fmt.Printf("solana_lp_open_canary_position_saved id=%s open_tx=%s action=%s est_fee_24h_usd=%s range_width_bps=%s\n",
		shortAddress(openBuild.PositionNFT.PublicKey().String()),
		shortAddress(signature),
		preflight.ExitSignal.Action,
		preflight.FeeProjection.EstimatedFee24hUSD.StringFixed(6),
		preflight.RangeSummary.WidthBPS.StringFixed(2),
	)
	return nil
}

func simulateSignedSolanaOpenPosition(ctx context.Context, cfg *config.Config, openBuild pancakeswapSolanaOpenPositionBuild) error {
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	simResp, simErr := client.SimulateTransactionWithOpts(ctx, openBuild.Tx, &solrpc.SimulateTransactionOpts{
		SigVerify:              false,
		Commitment:             solrpc.CommitmentProcessed,
		ReplaceRecentBlockhash: true,
	})
	if simErr != nil {
		return fmt.Errorf("solana lp open canary simulation failed: %w", simErr)
	}
	if simResp == nil || simResp.Value == nil {
		return fmt.Errorf("solana lp open canary simulation returned empty response")
	}
	if simResp.Value.Err != nil {
		fmt.Printf("solana_lp_open_canary_simulation ready=false units=%d err=%v\n", derefUint64(simResp.Value.UnitsConsumed), simResp.Value.Err)
		for i, line := range simResp.Value.Logs {
			if i >= 8 {
				fmt.Printf("solana_lp_open_canary_simulation_log more=%d\n", len(simResp.Value.Logs)-i)
				break
			}
			fmt.Printf("solana_lp_open_canary_simulation_log index=%d msg=%q\n", i, line)
		}
		return fmt.Errorf("solana lp open canary simulation rejected: %v", simResp.Value.Err)
	}
	fmt.Printf("solana_lp_open_canary_simulation ready=true units=%d logs=%d\n", derefUint64(simResp.Value.UnitsConsumed), len(simResp.Value.Logs))
	return nil
}

func waitForDirectSolanaConfirmation(ctx context.Context, client *solrpc.Client, txHash solanago.Signature) error {
	deadline := time.Now().Add(90 * time.Second)
	for {
		if time.Now().After(deadline) {
			return errors.New("Solana confirmation timeout")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
		result, err := client.GetSignatureStatuses(ctx, true, txHash)
		if err != nil || result == nil || len(result.Value) == 0 || result.Value[0] == nil {
			continue
		}
		status := result.Value[0]
		if status.Err != nil {
			return fmt.Errorf("solana signature status returned error: %v", status.Err)
		}
		if status.ConfirmationStatus == solrpc.ConfirmationStatusConfirmed || status.ConfirmationStatus == solrpc.ConfirmationStatusFinalized {
			return nil
		}
	}
}
