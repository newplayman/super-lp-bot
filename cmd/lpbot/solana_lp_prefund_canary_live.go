//go:build live

package main

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	solrpc "github.com/gagliardetto/solana-go/rpc"
	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const solanaLPPrefundCanaryMaxTotalUSD = 10.0
const solanaLPPrefundFollowupTimeout = 45 * time.Second
const solanaLPPrefundFollowupPollInterval = 3 * time.Second

func runSolanaLPPrefundCanary(ctx context.Context, cfg *config.Config, userPublicKey string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) error {
	if cfg == nil {
		return fmt.Errorf("config is required")
	}
	quotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaSOLUSDCLPFundingPlan(ctx, cfg, userPublicKey, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
	if err != nil {
		return err
	}
	printSolanaLPFundingPlan(plan)
	if !plan.TargetTotalUSD.LessThanOrEqual(domain.MustDecimal(fmt.Sprintf("%.0f", solanaLPPrefundCanaryMaxTotalUSD))) {
		return fmt.Errorf("solana lp prefund canary max total usd is %.0f", solanaLPPrefundCanaryMaxTotalUSD)
	}
	if plan.Status != "requires_prefund_swap" {
		return fmt.Errorf("solana lp prefund canary requires prefund path; status=%s blocker=%s", plan.Status, plan.Blocker)
	}
	prefund := plan.Prefund
	if prefund.FundingMint != solanaWrappedSOLAddress || prefund.TargetMint != solanaUSDCAddress {
		return fmt.Errorf("solana lp prefund canary only supports %s -> %s", solanaWrappedSOLAddress, solanaUSDCAddress)
	}

	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()

	quote, built, err := buildJupiterSwapTransaction(ctx, prefund.Wallet, prefund.FundingMint, prefund.TargetMint, fmt.Sprintf("%d", prefund.FundingAmountInRaw), slippageBPS, maxPriorityLamports)
	if err != nil {
		return err
	}
	maxPrefundOutRaw := uint64(solanaLPPrefundCanaryMaxTotalUSD * 1_000_000)
	quoteOutRaw, err := strconv.ParseUint(quote.OutAmount, 10, 64)
	if err != nil {
		return fmt.Errorf("parse solana lp prefund quote out amount: %w", err)
	}
	if quoteOutRaw > maxPrefundOutRaw {
		return fmt.Errorf("solana lp prefund canary max prefund output is %d raw USDC", maxPrefundOutRaw)
	}
	if len(built.SimulationError) > 0 && string(built.SimulationError) != "null" {
		return fmt.Errorf("solana lp prefund canary blocked by simulation: %s", compactJSON(built.SimulationError))
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

	openBuild, err := buildPancakeSolanaOpenPositionTransaction(ctx, cfg, solanaKnownSOLUSDCPool, plan)
	if err != nil {
		return fmt.Errorf("lp build before prefund broadcast failed: %w", err)
	}
	if _, err := signPancakeSolanaOpenPositionTransaction(openBuild.Tx, key, openBuild.PositionNFT); err != nil {
		return fmt.Errorf("lp sign before prefund broadcast failed: %w", err)
	}
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	simResp, simErr := client.SimulateTransactionWithOpts(ctx, openBuild.Tx, &solrpc.SimulateTransactionOpts{SigVerify: false, Commitment: solrpc.CommitmentProcessed, ReplaceRecentBlockhash: true})
	if simErr != nil {
		return fmt.Errorf("lp simulation before prefund broadcast failed: %w", simErr)
	}
	if simResp == nil || simResp.Value == nil {
		return fmt.Errorf("lp simulation before prefund broadcast returned empty response")
	}
	if simResp.Value.Err != nil {
		logs := strings.ToLower(strings.Join(simResp.Value.Logs, "\n"))
		if !strings.Contains(logs, "insufficient funds") {
			return fmt.Errorf("lp simulation has non-prefund blocker: %v", simResp.Value.Err)
		}
	}

	_, signedBytes, signature, err := signJupiterSwapTransaction(built.SwapTransaction, key)
	if err != nil {
		return err
	}
	broadcaster, err := livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:          strings.TrimSpace(cfg.Chains.Base.RPCPrimary),
		SolanaRPCURL:        solanaReadinessEndpoint(cfg),
		Confirmations:       cfg.Chains.Base.Confirmations,
		SolanaSkipPreflight: cfg.Chains.Solana.SkipPreflight,
	})
	if err != nil {
		return fmt.Errorf("initialize solana live broadcaster: %w", err)
	}
	signedTx := domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:     "solana-lp-prefund-canary-" + signature,
			Chain:  domain.ChainSolana,
			From:   domain.MustParseAddress(pub),
			To:     domain.MustParseAddress(prefund.TargetMint),
			MinOut: domain.MustDecimal(quote.OtherAmountThreshold),
		},
		Signature: signedBytes,
		Hash:      signature,
		Status:    domain.TxBuilt,
	}
	if err := state.Record(ctx, canaryEvent{
		Chain:           domain.ChainSolana.String(),
		Command:         "solana_lp_prefund_canary",
		Stage:           "signed",
		Status:          "ok",
		Wallet:          pub,
		TxHash:          signature,
		InputMint:       prefund.FundingMint,
		OutputMint:      prefund.TargetMint,
		InputAmountRaw:  quote.InAmount,
		OutputAmountRaw: quote.OutAmount,
		Message:         fmt.Sprintf("signed LP prefund %s -> %s in=%s out=%s", shortAddress(prefund.FundingMint), shortAddress(prefund.TargetMint), quote.InAmount, quote.OutAmount),
		CreatedAt:       time.Now().Unix(),
	}); err != nil {
		return fmt.Errorf("record solana lp prefund signed event: %w", err)
	}
	if err := state.RecordSignedTx(ctx, signedTx, domain.TxBuilt); err != nil {
		return fmt.Errorf("record solana lp prefund built tx: %w", err)
	}
	fmt.Printf("solana_lp_prefund_canary_prepare source=%s user=%s in_amount=%s out_amount=%s tx_base64_len=%d signed_bytes=%d signature=%s\n", keySource, shortAddress(pub), quote.InAmount, quote.OutAmount, len(built.SwapTransaction), len(signedBytes), shortAddress(signature))
	if err := broadcaster.Send(ctx, signedTx); err != nil {
		return fmt.Errorf("broadcast solana lp prefund canary: %w", err)
	}
	snapshot, err := fetchSolanaWalletSnapshot(ctx, cfg, pub)
	if err != nil {
		return fmt.Errorf("fetch solana lp prefund wallet snapshot: %w", err)
	}
	if err := state.RecordSignedTx(ctx, signedTx, domain.TxBroadcast); err != nil {
		return fmt.Errorf("record solana lp prefund broadcast tx: %w", err)
	}
	if err := state.Record(ctx, canaryEvent{
		Chain:           domain.ChainSolana.String(),
		Command:         "solana_lp_prefund_canary",
		Stage:           "broadcast",
		Status:          "ok",
		Wallet:          pub,
		TxHash:          signature,
		InputMint:       prefund.FundingMint,
		OutputMint:      prefund.TargetMint,
		InputAmountRaw:  quote.InAmount,
		OutputAmountRaw: quote.OutAmount,
		SOLBalanceRaw:   fmt.Sprintf("%d", snapshot.SOLBalanceRaw),
		USDCBalanceRaw:  fmt.Sprintf("%d", snapshot.USDCBalanceRaw),
		Message:         fmt.Sprintf("broadcast LP prefund %s -> %s in=%s out=%s", shortAddress(prefund.FundingMint), shortAddress(prefund.TargetMint), quote.InAmount, quote.OutAmount),
		CreatedAt:       time.Now().Unix(),
	}); err != nil {
		return fmt.Errorf("record solana lp prefund broadcast event: %w", err)
	}
	fmt.Printf("solana_lp_prefund_canary_broadcast success=true signature=%s in_amount=%s out_amount=%s\n", signature, quote.InAmount, quote.OutAmount)
	if err := followUpSolanaLPPrefundCanary(ctx, cfg, pub, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, snapshot.USDCBalanceRaw); err != nil {
		return err
	}
	return nil
}

func followUpSolanaLPPrefundCanary(ctx context.Context, cfg *config.Config, wallet string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, baselineUSDC uint64) error {
	deadline := time.Now().Add(solanaLPPrefundFollowupTimeout)
	for {
		snapshot, err := fetchSolanaWalletSnapshot(ctx, cfg, wallet)
		if err == nil {
			deltaUSDC := uint64(0)
			if snapshot.USDCBalanceRaw > baselineUSDC {
				deltaUSDC = snapshot.USDCBalanceRaw - baselineUSDC
			}
			fmt.Printf("solana_lp_prefund_followup_balance sol_raw=%d usdc_raw=%d delta_usdc_raw=%d\n",
				snapshot.SOLBalanceRaw,
				snapshot.USDCBalanceRaw,
				deltaUSDC,
			)
			if deltaUSDC > 0 {
				quotes := newSolanaFundingQuoteClient()
				plan, planErr := estimateSolanaSOLUSDCLPFundingPlan(ctx, cfg, wallet, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
				if planErr != nil {
					return fmt.Errorf("solana lp prefund follow-up plan failed: %w", planErr)
				}
				printSolanaLPFundingPlan(plan)
				openBuild, buildErr := buildPancakeSolanaOpenPositionTransaction(ctx, cfg, solanaKnownSOLUSDCPool, plan)
				if buildErr != nil {
					return fmt.Errorf("solana lp prefund follow-up build failed: %w", buildErr)
				}
				fmt.Printf("solana_lp_prefund_followup_build ready=true amount0_max=%d amount1_max=%d base_flag=%t nft_mint=%s\n",
					openBuild.Amount0Max,
					openBuild.Amount1Max,
					openBuild.BaseFlag,
					shortAddress(openBuild.PositionNFT.PublicKey().String()),
				)
				key, _, ok, keyErr := loadSolanaPrivateKeyFromEnv()
				if keyErr != nil {
					return keyErr
				}
				if !ok {
					return fmt.Errorf("missing signer env during solana lp prefund follow-up")
				}
				if _, signErr := signPancakeSolanaOpenPositionTransaction(openBuild.Tx, key, openBuild.PositionNFT); signErr != nil {
					return fmt.Errorf("solana lp prefund follow-up sign failed: %w", signErr)
				}
				client := solrpc.New(solanaReadinessEndpoint(cfg))
				simResp, simErr := client.SimulateTransactionWithOpts(ctx, openBuild.Tx, &solrpc.SimulateTransactionOpts{
					SigVerify:              false,
					Commitment:             solrpc.CommitmentProcessed,
					ReplaceRecentBlockhash: true,
				})
				if simErr != nil {
					return fmt.Errorf("solana lp prefund follow-up simulation failed: %w", simErr)
				}
				if simResp == nil || simResp.Value == nil {
					return fmt.Errorf("solana lp prefund follow-up simulation returned empty response")
				}
				if simResp.Value.Err != nil {
					fmt.Printf("solana_lp_prefund_followup_simulation ready=false units=%d err=%v\n", derefUint64(simResp.Value.UnitsConsumed), simResp.Value.Err)
					for i, line := range simResp.Value.Logs {
						if i >= 8 {
							fmt.Printf("solana_lp_prefund_followup_simulation_log more=%d\n", len(simResp.Value.Logs)-i)
							break
						}
						fmt.Printf("solana_lp_prefund_followup_simulation_log index=%d msg=%q\n", i, line)
					}
					return fmt.Errorf("solana lp prefund follow-up still blocked: %v", simResp.Value.Err)
				}
				fmt.Printf("solana_lp_prefund_followup_simulation ready=true units=%d logs=%d\n", derefUint64(simResp.Value.UnitsConsumed), len(simResp.Value.Logs))
				return nil
			}
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("solana lp prefund follow-up timed out waiting for post-broadcast balance update")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(solanaLPPrefundFollowupPollInterval):
		}
	}
}
