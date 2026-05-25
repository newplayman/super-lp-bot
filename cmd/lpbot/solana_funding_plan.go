package main

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"math/big"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	solanago "github.com/gagliardetto/solana-go"
	ata "github.com/gagliardetto/solana-go/programs/associated-token-account"
	systemprog "github.com/gagliardetto/solana-go/programs/system"
	tokenprog "github.com/gagliardetto/solana-go/programs/token"
	solrpc "github.com/gagliardetto/solana-go/rpc"
	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

const solanaFundingMinReserveLamports uint64 = 10000000
const solanaBaseNetworkFeeLamports uint64 = 5000
const solanaUSDCDecimals = 1000000
const solanaSOLDecimals = 1000000000
const solanaFundingQuoteMinGap = 350 * time.Millisecond
const solanaFundingQuoteCooldown = 20 * time.Second
const solanaFundingQuoteRetryGap = 1500 * time.Millisecond
const pancakeswapSolanaCLMMProgramID = "HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq"
const solanaMemoProgramID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

var (
	pancakeOpenPositionWithToken22NftDiscriminator = []byte{77, 255, 174, 82, 125, 29, 201, 46}
	pancakeClosePositionDiscriminator              = []byte{123, 134, 81, 0, 49, 68, 98, 98}
	pancakeDecreaseLiquidityV2Discriminator        = []byte{58, 127, 188, 62, 79, 82, 196, 96}
)

type solanaFundingPlan struct {
	Wallet                    string
	TargetMint                string
	TargetAmountRaw           uint64
	Status                    string
	Blocker                   string
	DirectBalanceRaw          uint64
	DirectShortfallRaw        uint64
	SOLBalanceRaw             uint64
	USDCBalanceRaw            uint64
	ReservedSOLLamports       uint64
	EstimatedSOLPriceUSDC     domain.Decimal
	EstimatedChainValueUSDC   domain.Decimal
	FundingMint               string
	FundingAmountInRaw        uint64
	FundingExpectedOutRaw     uint64
	FundingThresholdOutRaw    uint64
	FundingPriceImpactPct     string
	FundingSwapCostUSDC       domain.Decimal
	FundingMaxSlippageUSDC    domain.Decimal
	FundingNetworkFeeLamports uint64
	FundingNetworkFeeUSDC     domain.Decimal
}

type solanaLPFundingPlan struct {
	Wallet                  string
	Token0                  string
	Token1                  string
	TargetTotalUSD          domain.Decimal
	TargetToken0Raw         uint64
	TargetToken1Raw         uint64
	Status                  string
	Blocker                 string
	SOLBalanceRaw           uint64
	USDCBalanceRaw          uint64
	ReservedSOLLamports     uint64
	EstimatedSOLPriceUSDC   domain.Decimal
	EstimatedChainValueUSDC domain.Decimal
	Prefund                 solanaFundingPlan
}

type solanaLPPreflight struct {
	Plan                    solanaLPFundingPlan
	FundingReady            bool
	PrefundSwapBuildReady   bool
	PrefundSwapSignReady    bool
	PostPrefundBalanceReady bool
	LPBuildReady            bool
	LPSignReady             bool
	LPSimReady              bool
	SequencedPathReady      bool
	PoolID                  string
	PoolProtocol            string
	PreferredPoolID         string
	PreferredProtocol       string
	PoolDiscovery           *ports.PoolDiscovery
	ExistingPositionID      string
	ExistingPositionStatus  string
	LPBuildBase64Len        int
	LPSignature             string
	PositionNFTMint         string
	LPSimUnits              uint64
	LPSimErr                string
	RangeSummary            solanaLPRangeSummary
	FeeProjection           solanaLPFeeProjection
	ExitSignal              solanaLPExitSignal
	PostPrefundSOLRaw       uint64
	PostPrefundUSDCRaw      uint64
	Blocker                 string
}

type pancakeswapSolanaPoolState struct {
	PoolID        solanago.PublicKey
	AmmConfig     solanago.PublicKey
	TokenMint0    solanago.PublicKey
	TokenMint1    solanago.PublicKey
	TokenVault0   solanago.PublicKey
	TokenVault1   solanago.PublicKey
	MintDecimals0 uint8
	MintDecimals1 uint8
	TickSpacing   uint16
	TradeFeeBPS   uint
	SqrtPriceX64  uint64
	CurrentTick   int32
	RewardInfos   []pancakeswapSolanaRewardInfo
}

type pancakeswapSolanaRewardInfo struct {
	Index      int
	TokenMint  solanago.PublicKey
	TokenVault solanago.PublicKey
}

type pancakeswapSolanaPersonalPositionState struct {
	NFTMint           solanago.PublicKey
	PoolID            solanago.PublicKey
	TickLower         int32
	TickUpper         int32
	LiquidityRaw      string
	TokenFeesOwed0    uint64
	TokenFeesOwed1    uint64
	RewardAmountsOwed []uint64
}

type pancakeswapSolanaOpenPositionBuild struct {
	Tx              *solanago.Transaction
	TxBytes         []byte
	TxBase64        string
	PositionNFT     solanago.PrivateKey
	PoolState       pancakeswapSolanaPoolState
	TickLower       int32
	TickUpper       int32
	BaseFlag        bool
	Amount0Max      uint64
	Amount1Max      uint64
	WrapSOLRequired bool
}

type pancakeswapSolanaClosePositionBuild struct {
	Tx           *solanago.Transaction
	TxBytes      []byte
	TxBase64     string
	PoolState    pancakeswapSolanaPoolState
	TokenProgram solanago.PublicKey
}

type pancakeswapSolanaDecreaseLiquidityBuild struct {
	Tx           *solanago.Transaction
	TxBytes      []byte
	TxBase64     string
	PoolState    pancakeswapSolanaPoolState
	LiquidityRaw string
	TickLower    int32
	TickUpper    int32
}

type solanaFundingQuoteClient struct {
	mu            sync.Mutex
	cache         map[string]jupiterQuoteSummary
	lastRequest   time.Time
	cooldownUntil time.Time
}

func newSolanaFundingQuoteClient() *solanaFundingQuoteClient {
	return &solanaFundingQuoteClient{
		cache: make(map[string]jupiterQuoteSummary),
	}
}

func runSolanaFundingPlan(ctx context.Context, cfg *config.Config, userPublicKey string, targetMint string, amountRaw string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, ledgerPositionID string) error {
	quotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaFundingPlan(ctx, cfg, userPublicKey, targetMint, amountRaw, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
	if err != nil {
		return err
	}
	printSolanaFundingPlan(plan)
	if err := maybeAppendEstimatedFundingLedgerEntries(ctx, cfg, strings.TrimSpace(ledgerPositionID), plan.FundingSwapCostUSDC, plan.FundingNetworkFeeUSDC, plan.FundingMaxSlippageUSDC); err != nil {
		return err
	}
	return nil
}

func runSolanaLPFundingPlan(ctx context.Context, cfg *config.Config, userPublicKey string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, ledgerPositionID string) error {
	quotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaSOLUSDCLPFundingPlan(ctx, cfg, userPublicKey, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
	if err != nil {
		return err
	}
	printSolanaLPFundingPlan(plan)
	if err := maybeAppendEstimatedFundingLedgerEntries(ctx, cfg, strings.TrimSpace(ledgerPositionID), plan.Prefund.FundingSwapCostUSDC, plan.Prefund.FundingNetworkFeeUSDC, plan.Prefund.FundingMaxSlippageUSDC); err != nil {
		return err
	}
	return nil
}

func runSolanaLPPreflight(ctx context.Context, cfg *config.Config, userPublicKey string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) error {
	if err := maybeBackfillLatestSolanaOpenCanaryPosition(ctx, cfg, maxPriorityLamports); err != nil {
		fmt.Printf("solana_lp_backfill warning=%q\n", err)
	}
	quotes := newSolanaFundingQuoteClient()
	plan, err := estimateSolanaSOLUSDCLPFundingPlan(ctx, cfg, userPublicKey, totalUSD, slippageBPS, maxPriorityLamports, reserveLamports, quotes)
	if err != nil {
		return err
	}
	printSolanaLPFundingPlan(plan)
	result := solanaLPPreflight{Plan: plan}
	if pool, err := discoverPreferredSolanaLPPool(ctx); err == nil && pool != nil {
		result.PoolID = pool.ID
		result.PoolProtocol = pool.Protocol
		result.PoolDiscovery = pool
		fmt.Printf("solana_lp_pool_candidate id=%s protocol=%s tvl_usd=%s vol24h_usd=%s token0=%s token1=%s\n",
			pool.ID,
			pool.Protocol,
			pool.TVLUSD.String(),
			pool.Vol24h.String(),
			shortAddress(pool.Token0.String()),
			shortAddress(pool.Token1.String()),
		)
	}
	if pool, err := discoverPreferredSolanaProtocolPool(ctx); err == nil && pool != nil {
		result.PreferredPoolID = pool.ID
		result.PreferredProtocol = pool.Protocol
		fmt.Printf("solana_lp_protocol_priority_candidate id=%s protocol=%s tvl_usd=%s vol24h_usd=%s token0=%s token1=%s\n",
			pool.ID,
			pool.Protocol,
			pool.TVLUSD.String(),
			pool.Vol24h.String(),
			shortAddress(pool.Token0.String()),
			shortAddress(pool.Token1.String()),
		)
	}
	if strings.TrimSpace(result.PoolID) == "" {
		result.PoolID = solanaKnownSOLUSDCPool
		result.PoolProtocol = "pancakeswap-v3-solana"
		fmt.Printf("solana_lp_pool_candidate_fallback id=%s protocol=%s reason=%q\n", result.PoolID, result.PoolProtocol, "known_sol_usdc_pool")
	}
	if strings.TrimSpace(result.PreferredPoolID) == "" {
		result.PreferredPoolID = result.PoolID
		result.PreferredProtocol = result.PoolProtocol
		fmt.Printf("solana_lp_protocol_priority_candidate_fallback id=%s protocol=%s reason=%q\n", result.PreferredPoolID, result.PreferredProtocol, "known_sol_usdc_pool")
	}
	if cfg != nil && strings.TrimSpace(cfg.Store.PostgresDSN) != "" {
		store, storeErr := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
		if storeErr == nil {
			if existing, existingErr := findExistingOpenSolanaPositionForPool(ctx, store.DB(), result.PoolID); existingErr == nil && existing != nil {
				if refreshed, refreshErr := refreshExistingSolanaOpenPositionMetadata(ctx, cfg, store.DB(), existing, result.PoolDiscovery, maxPriorityLamports); refreshErr == nil && refreshed != nil {
					existing = refreshed
				}
				result.ExistingPositionID = existing.ID
				result.ExistingPositionStatus = string(existing.Status)
				if strings.TrimSpace(result.PoolID) == "" {
					result.PoolID = existing.PoolID
				}
				if strings.TrimSpace(result.PoolProtocol) == "" {
					result.PoolProtocol = existing.Protocol
				}
				if meta, ok := loadSolanaLPPositionMetadata(existing); ok {
					applySolanaLPMetadataToPreflight(&result, existing, meta)
				}
				result.Blocker = fmt.Sprintf("solana_existing_open_position id=%s status=%s", existing.ID, existing.Status)
			}
			_ = store.Close()
		}
	}
	if strings.TrimSpace(result.ExistingPositionID) != "" {
		printSolanaLPPreflight(result)
		return nil
	}
	switch plan.Status {
	case "ready_direct":
		result.FundingReady = true
		fallthrough
	case "requires_prefund_swap":
		result.FundingReady = true
		if plan.Status == "requires_prefund_swap" {
			prefund := plan.Prefund
			_, built, err := buildJupiterSwapTransaction(ctx, prefund.Wallet, prefund.FundingMint, prefund.TargetMint, strconv.FormatUint(prefund.FundingAmountInRaw, 10), slippageBPS, maxPriorityLamports)
			if err != nil {
				result.Blocker = fmt.Sprintf("prefund_swap_build_failed: %v", err)
				printSolanaLPPreflight(result)
				return nil
			}
			if len(built.SimulationError) > 0 && string(built.SimulationError) != "null" {
				result.Blocker = fmt.Sprintf("prefund_swap_simulation: %s", compactJSON(built.SimulationError))
				printSolanaLPPreflight(result)
				return nil
			}
			result.PrefundSwapBuildReady = true
			key, keySource, ok, err := loadSolanaPrivateKeyFromEnv()
			if err == nil && ok {
				if _, _, signature, signErr := signJupiterSwapTransaction(built.SwapTransaction, key); signErr == nil {
					result.PrefundSwapSignReady = true
					fmt.Printf("solana_lp_prefund_swap_sign_readiness ready=true source=%s signature=%s\n", keySource, shortAddress(signature))
				}
			}
		}
		fallthrough
	case "ready_direct_lp":
		if strings.EqualFold(result.PoolProtocol, "pancakeswap-v3-solana") && strings.TrimSpace(result.PoolID) != "" {
			openBuild, buildErr := buildPancakeSolanaOpenPositionTransaction(ctx, cfg, result.PoolID, plan)
			if buildErr != nil {
				result.Blocker = fmt.Sprintf("solana_pancakeswap_v3_solana_open_position_build_failed: %v", buildErr)
				printSolanaLPPreflight(result)
				return nil
			}
			result.LPBuildReady = true
			result.LPBuildBase64Len = len(openBuild.TxBase64)
			result.PositionNFTMint = openBuild.PositionNFT.PublicKey().String()
			result.PostPrefundSOLRaw, result.PostPrefundUSDCRaw, result.PostPrefundBalanceReady = evaluateSolanaPostPrefundBalances(plan, openBuild)
			result.RangeSummary, result.FeeProjection, result.ExitSignal = computeSolanaLPAnalytics(ctx, result.PoolID, result.PoolProtocol, result.PoolDiscovery, openBuild.PoolState, openBuild.TickLower, openBuild.TickUpper, plan.TargetTotalUSD, maxPriorityLamports)
			fmt.Printf("solana_lp_open_position_build ready=true protocol=%s pool_id=%s tick_lower=%d tick_upper=%d amount0_max=%d amount1_max=%d wrap_sol_required=%t tx_base64_len=%d nft_mint=%s\n",
				result.PoolProtocol,
				result.PoolID,
				openBuild.TickLower,
				openBuild.TickUpper,
				openBuild.Amount0Max,
				openBuild.Amount1Max,
				openBuild.WrapSOLRequired,
				len(openBuild.TxBase64),
				shortAddress(result.PositionNFTMint),
			)
			fmt.Printf("solana_lp_open_position_quote base_flag=%t\n", openBuild.BaseFlag)
			fmt.Printf("solana_lp_post_prefund_balances ready=%t sol_raw=%d usdc_raw=%d\n", result.PostPrefundBalanceReady, result.PostPrefundSOLRaw, result.PostPrefundUSDCRaw)
			if key, keySource, ok, err := loadSolanaPrivateKeyFromEnv(); err == nil && ok {
				if signature, signErr := signPancakeSolanaOpenPositionTransaction(openBuild.Tx, key, openBuild.PositionNFT); signErr == nil {
					result.LPSignReady = true
					result.LPSignature = signature
					fmt.Printf("solana_lp_open_position_sign_readiness ready=true source=%s signature=%s nft_mint=%s\n", keySource, shortAddress(signature), shortAddress(result.PositionNFTMint))
					client := solrpc.New(solanaReadinessEndpoint(cfg))
					simResp, simErr := client.SimulateTransactionWithOpts(ctx, openBuild.Tx, &solrpc.SimulateTransactionOpts{
						SigVerify:              false,
						Commitment:             solrpc.CommitmentProcessed,
						ReplaceRecentBlockhash: true,
					})
					if simErr != nil {
						result.Blocker = fmt.Sprintf("solana_pancakeswap_v3_solana_open_position_simulation_failed: %v", simErr)
					} else if simResp == nil || simResp.Value == nil {
						result.Blocker = "solana_pancakeswap_v3_solana_open_position_simulation_empty"
					} else if simResp.Value.Err != nil {
						result.LPSimErr = fmt.Sprintf("%v", simResp.Value.Err)
						result.Blocker = fmt.Sprintf("solana_pancakeswap_v3_solana_open_position_simulation_rejected: %v", simResp.Value.Err)
						fmt.Printf("solana_lp_open_position_simulation ready=false units=%d err=%q\n", derefUint64(simResp.Value.UnitsConsumed), result.LPSimErr)
						for i, line := range simResp.Value.Logs {
							if i >= 12 {
								fmt.Printf("solana_lp_open_position_simulation_log more=%d\n", len(simResp.Value.Logs)-i)
								break
							}
							fmt.Printf("solana_lp_open_position_simulation_log index=%d msg=%q\n", i, line)
						}
						if len(simResp.Value.Logs) > 12 {
							start := len(simResp.Value.Logs) - 12
							if start < 12 {
								start = 12
							}
							for i := start; i < len(simResp.Value.Logs); i++ {
								fmt.Printf("solana_lp_open_position_simulation_log_tail index=%d msg=%q\n", i, simResp.Value.Logs[i])
							}
						}
						if strings.Contains(strings.ToLower(strings.Join(simResp.Value.Logs, "\n")), "insufficient funds") && plan.Status == "requires_prefund_swap" {
							result.Blocker = "solana_lp_requires_prefund_execution_before_lp"
						}
					} else {
						result.LPSimReady = true
						result.LPSimUnits = derefUint64(simResp.Value.UnitsConsumed)
						fmt.Printf("solana_lp_open_position_simulation ready=true units=%d logs=%d\n", derefUint64(simResp.Value.UnitsConsumed), len(simResp.Value.Logs))
						result.Blocker = ""
					}
					if result.PrefundSwapSignReady && result.PostPrefundBalanceReady {
						result.SequencedPathReady = true
					}
				} else {
					result.Blocker = fmt.Sprintf("solana_pancakeswap_v3_solana_open_position_sign_failed: %v", signErr)
				}
			} else {
				result.Blocker = "solana_pancakeswap_v3_solana_open_position_signer_missing"
			}
			printSolanaLPPreflight(result)
			return nil
		}
		result.Blocker = solanaLPExecutionBlocker(result.PoolProtocol)
	default:
		result.Blocker = plan.Blocker
	}
	printSolanaLPPreflight(result)
	return nil
}

func estimateSolanaFundingPlan(ctx context.Context, cfg *config.Config, userPublicKey string, targetMint string, amountRaw string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, quotes *solanaFundingQuoteClient) (solanaFundingPlan, error) {
	wallet, err := resolveSolanaSwapUserPublicKey(userPublicKey)
	if err != nil {
		return solanaFundingPlan{}, err
	}
	targetMint = strings.TrimSpace(targetMint)
	if targetMint == "" {
		targetMint = solanaUSDCAddress
	}
	targetAmount, err := strconv.ParseUint(strings.TrimSpace(amountRaw), 10, 64)
	if err != nil || targetAmount == 0 {
		return solanaFundingPlan{}, fmt.Errorf("invalid funding amount raw %q", amountRaw)
	}
	if reserveLamports == 0 {
		reserveLamports = solanaFundingMinReserveLamports
	}
	snapshot, err := fetchSolanaWalletSnapshot(ctx, cfg, wallet)
	if err != nil {
		return solanaFundingPlan{}, err
	}
	solPriceUSDC, err := fetchSolanaSpotPriceUSDC(ctx, slippageBPS, quotes)
	if err != nil {
		return solanaFundingPlan{}, err
	}
	chainValueUSDC := rawUSDCToDecimal(snapshot.USDCBalanceRaw).Add(rawSOLToDecimal(snapshot.SOLBalanceRaw).Mul(solPriceUSDC))
	plan := solanaFundingPlan{
		Wallet:                    wallet,
		TargetMint:                targetMint,
		TargetAmountRaw:           targetAmount,
		SOLBalanceRaw:             snapshot.SOLBalanceRaw,
		USDCBalanceRaw:            snapshot.USDCBalanceRaw,
		ReservedSOLLamports:       reserveLamports,
		EstimatedSOLPriceUSDC:     solPriceUSDC,
		EstimatedChainValueUSDC:   chainValueUSDC,
		FundingNetworkFeeLamports: maxPriorityLamports + solanaBaseNetworkFeeLamports,
	}
	plan.FundingNetworkFeeUSDC = rawSOLToDecimal(plan.FundingNetworkFeeLamports).Mul(solPriceUSDC)
	if snapshot.SOLBalanceRaw <= reserveLamports+plan.FundingNetworkFeeLamports {
		plan.Status = "insufficient_chain_assets"
		plan.Blocker = "insufficient_sol_for_gas_reserve"
		plan.DirectBalanceRaw = solanaWalletMintBalance(snapshot, targetMint)
		if plan.DirectBalanceRaw < targetAmount {
			plan.DirectShortfallRaw = targetAmount - plan.DirectBalanceRaw
		}
		return plan, nil
	}
	plan.DirectBalanceRaw = solanaWalletMintBalance(snapshot, targetMint)
	if targetMint == solanaWrappedSOLAddress {
		spendableSOL := snapshot.SOLBalanceRaw - reserveLamports - plan.FundingNetworkFeeLamports
		if spendableSOL >= targetAmount {
			plan.Status = "ready_direct"
			return plan, nil
		}
		plan.DirectShortfallRaw = targetAmount - spendableSOL
	} else if plan.DirectBalanceRaw >= targetAmount {
		plan.Status = "ready_direct"
		return plan, nil
	}
	if plan.DirectShortfallRaw == 0 {
		plan.DirectShortfallRaw = targetAmount - plan.DirectBalanceRaw
	}

	switch targetMint {
	case solanaUSDCAddress:
		availableSOL := uint64(0)
		if snapshot.SOLBalanceRaw > reserveLamports+plan.FundingNetworkFeeLamports {
			availableSOL = snapshot.SOLBalanceRaw - reserveLamports - plan.FundingNetworkFeeLamports
		}
		if availableSOL == 0 {
			plan.Status = "insufficient_chain_assets"
			plan.Blocker = "no_sol_available_after_reserve"
			return plan, nil
		}
		quote, amountInRaw, err := findExactInQuoteForTargetOut(ctx, solanaWrappedSOLAddress, solanaUSDCAddress, plan.DirectShortfallRaw, availableSOL, slippageBPS, solPriceUSDC, quotes)
		if err != nil {
			plan.Status = "funding_path_unavailable"
			plan.Blocker = err.Error()
			return plan, nil
		}
		plan.Status = "requires_prefund_swap"
		plan.FundingMint = solanaWrappedSOLAddress
		plan.FundingAmountInRaw = amountInRaw
		plan.FundingExpectedOutRaw = mustParseUint64(quote.OutAmount)
		plan.FundingThresholdOutRaw = mustParseUint64(quote.OtherAmountThreshold)
		plan.FundingPriceImpactPct = strings.TrimSpace(quote.PriceImpactPct)
		plan.FundingMaxSlippageUSDC = rawUSDCToDecimal(diffUint64(plan.FundingExpectedOutRaw, plan.FundingThresholdOutRaw))
		inputValueUSDC := rawSOLToDecimal(amountInRaw).Mul(solPriceUSDC)
		outputValueUSDC := rawUSDCToDecimal(plan.FundingExpectedOutRaw)
		if inputValueUSDC.GreaterThan(outputValueUSDC) {
			plan.FundingSwapCostUSDC = inputValueUSDC.Sub(outputValueUSDC)
		}
		return plan, nil
	case solanaWrappedSOLAddress:
		availableUSDC := snapshot.USDCBalanceRaw
		if availableUSDC == 0 {
			plan.Status = "insufficient_chain_assets"
			plan.Blocker = "no_usdc_available"
			return plan, nil
		}
		quote, amountInRaw, err := findExactInQuoteForTargetOut(ctx, solanaUSDCAddress, solanaWrappedSOLAddress, plan.DirectShortfallRaw, availableUSDC, slippageBPS, solPriceUSDC, quotes)
		if err != nil {
			plan.Status = "funding_path_unavailable"
			plan.Blocker = err.Error()
			return plan, nil
		}
		plan.Status = "requires_prefund_swap"
		plan.FundingMint = solanaUSDCAddress
		plan.FundingAmountInRaw = amountInRaw
		plan.FundingExpectedOutRaw = mustParseUint64(quote.OutAmount)
		plan.FundingThresholdOutRaw = mustParseUint64(quote.OtherAmountThreshold)
		plan.FundingPriceImpactPct = strings.TrimSpace(quote.PriceImpactPct)
		plan.FundingMaxSlippageUSDC = rawSOLToDecimal(diffUint64(plan.FundingExpectedOutRaw, plan.FundingThresholdOutRaw)).Mul(solPriceUSDC)
		inputValueUSDC := rawUSDCToDecimal(amountInRaw)
		outputValueUSDC := rawSOLToDecimal(plan.FundingExpectedOutRaw).Mul(solPriceUSDC)
		if inputValueUSDC.GreaterThan(outputValueUSDC) {
			plan.FundingSwapCostUSDC = inputValueUSDC.Sub(outputValueUSDC)
		}
		return plan, nil
	default:
		if snapshot.USDCBalanceRaw > 0 {
			quote, amountInRaw, err := findExactInQuoteForTargetOut(ctx, solanaUSDCAddress, targetMint, plan.DirectShortfallRaw, snapshot.USDCBalanceRaw, slippageBPS, solPriceUSDC, quotes)
			if err == nil {
				plan.Status = "requires_prefund_swap"
				plan.FundingMint = solanaUSDCAddress
				plan.FundingAmountInRaw = amountInRaw
				plan.FundingExpectedOutRaw = mustParseUint64(quote.OutAmount)
				plan.FundingThresholdOutRaw = mustParseUint64(quote.OtherAmountThreshold)
				plan.FundingPriceImpactPct = strings.TrimSpace(quote.PriceImpactPct)
				plan.FundingMaxSlippageUSDC = rawUSDCToDecimal(amountInRaw).Mul(domain.NewDecimalFromInt(int64(slippageBPS))).Div(domain.MustDecimal("10000"))
				return plan, nil
			}
		}
		availableSOL := uint64(0)
		if snapshot.SOLBalanceRaw > reserveLamports+plan.FundingNetworkFeeLamports {
			availableSOL = snapshot.SOLBalanceRaw - reserveLamports - plan.FundingNetworkFeeLamports
		}
		if availableSOL > 0 {
			quote, amountInRaw, err := findExactInQuoteForTargetOut(ctx, solanaWrappedSOLAddress, targetMint, plan.DirectShortfallRaw, availableSOL, slippageBPS, solPriceUSDC, quotes)
			if err == nil {
				plan.Status = "requires_prefund_swap"
				plan.FundingMint = solanaWrappedSOLAddress
				plan.FundingAmountInRaw = amountInRaw
				plan.FundingExpectedOutRaw = mustParseUint64(quote.OutAmount)
				plan.FundingThresholdOutRaw = mustParseUint64(quote.OtherAmountThreshold)
				plan.FundingPriceImpactPct = strings.TrimSpace(quote.PriceImpactPct)
				plan.FundingMaxSlippageUSDC = rawSOLToDecimal(amountInRaw).Mul(solPriceUSDC).Mul(domain.NewDecimalFromInt(int64(slippageBPS))).Div(domain.MustDecimal("10000"))
				return plan, nil
			}
		}
		plan.Status = "funding_path_unavailable"
		plan.Blocker = "no same-chain USDC/SOL route could fund target mint"
		return plan, nil
	}
}

func printSolanaFundingPlan(plan solanaFundingPlan) {
	fmt.Printf("solana_funding_plan wallet=%s chain=solana same_chain_only=true target=%s target_amount_raw=%d status=%s direct_balance_raw=%d shortfall_raw=%d reserve_sol_lamports=%d\n",
		shortAddress(plan.Wallet),
		shortAddress(plan.TargetMint),
		plan.TargetAmountRaw,
		plan.Status,
		plan.DirectBalanceRaw,
		plan.DirectShortfallRaw,
		plan.ReservedSOLLamports,
	)
	fmt.Printf("solana_funding_balances sol_raw=%d usdc_raw=%d sol_price_usdc=%s chain_value_usdc=%s\n",
		plan.SOLBalanceRaw,
		plan.USDCBalanceRaw,
		plan.EstimatedSOLPriceUSDC.StringFixed(6),
		plan.EstimatedChainValueUSDC.StringFixed(6),
	)
	if plan.Blocker != "" {
		fmt.Printf("solana_funding_blocker reason=%q\n", plan.Blocker)
	}
	if plan.Status != "requires_prefund_swap" {
		return
	}
	fmt.Printf("solana_prefund_swap from=%s to=%s amount_in_raw=%d expected_out_raw=%d threshold_out_raw=%d price_impact_pct=%s swap_cost_usdc=%s gas_lamports=%d gas_usdc=%s max_slippage_usdc=%s\n",
		shortAddress(plan.FundingMint),
		shortAddress(plan.TargetMint),
		plan.FundingAmountInRaw,
		plan.FundingExpectedOutRaw,
		plan.FundingThresholdOutRaw,
		plan.FundingPriceImpactPct,
		plan.FundingSwapCostUSDC.StringFixed(6),
		plan.FundingNetworkFeeLamports,
		plan.FundingNetworkFeeUSDC.StringFixed(6),
		plan.FundingMaxSlippageUSDC.StringFixed(6),
	)
}

func estimateSolanaSOLUSDCLPFundingPlan(ctx context.Context, cfg *config.Config, userPublicKey string, totalUSD string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64, quotes *solanaFundingQuoteClient) (solanaLPFundingPlan, error) {
	wallet, err := resolveSolanaSwapUserPublicKey(userPublicKey)
	if err != nil {
		return solanaLPFundingPlan{}, err
	}
	totalTargetUSD, err := decimalFromStringStrict(totalUSD)
	if err != nil || !totalTargetUSD.GreaterThan(domain.NewDecimalFromInt(0)) {
		return solanaLPFundingPlan{}, fmt.Errorf("invalid solana lp total usd %q", totalUSD)
	}
	if reserveLamports == 0 {
		reserveLamports = solanaFundingMinReserveLamports
	}
	snapshot, err := fetchSolanaWalletSnapshot(ctx, cfg, wallet)
	if err != nil {
		return solanaLPFundingPlan{}, err
	}
	solPriceUSDC, err := fetchSolanaSpotPriceUSDC(ctx, slippageBPS, quotes)
	if err != nil {
		return solanaLPFundingPlan{}, err
	}
	chainValueUSDC := rawUSDCToDecimal(snapshot.USDCBalanceRaw).Add(rawSOLToDecimal(snapshot.SOLBalanceRaw).Mul(solPriceUSDC))
	halfUSD := totalTargetUSD.Div(domain.NewDecimalFromInt(2))
	targetUSDCRaw := decimalToScaledUint64(halfUSD, solanaUSDCDecimals)
	targetSOLRaw := decimalToScaledUint64(halfUSD.Div(solPriceUSDC), solanaSOLDecimals)
	plan := solanaLPFundingPlan{
		Wallet:                  wallet,
		Token0:                  solanaWrappedSOLAddress,
		Token1:                  solanaUSDCAddress,
		TargetTotalUSD:          totalTargetUSD,
		TargetToken0Raw:         targetSOLRaw,
		TargetToken1Raw:         targetUSDCRaw,
		SOLBalanceRaw:           snapshot.SOLBalanceRaw,
		USDCBalanceRaw:          snapshot.USDCBalanceRaw,
		ReservedSOLLamports:     reserveLamports,
		EstimatedSOLPriceUSDC:   solPriceUSDC,
		EstimatedChainValueUSDC: chainValueUSDC,
	}
	requiredValue := totalTargetUSD.Add(rawSOLToDecimal(reserveLamports + maxPriorityLamports + solanaBaseNetworkFeeLamports).Mul(solPriceUSDC))
	if chainValueUSDC.LessThan(requiredValue) {
		plan.Status = "insufficient_chain_assets"
		plan.Blocker = "same_chain_total_value_below_lp_target_plus_reserve"
		return plan, nil
	}

	spendableSOL := uint64(0)
	if snapshot.SOLBalanceRaw > reserveLamports+maxPriorityLamports+solanaBaseNetworkFeeLamports {
		spendableSOL = snapshot.SOLBalanceRaw - reserveLamports - maxPriorityLamports - solanaBaseNetworkFeeLamports
	}
	if snapshot.USDCBalanceRaw >= targetUSDCRaw && spendableSOL >= targetSOLRaw {
		plan.Status = "ready_direct"
		return plan, nil
	}

	if snapshot.USDCBalanceRaw < targetUSDCRaw {
		availableSOLForUSDC := uint64(0)
		if spendableSOL > targetSOLRaw {
			availableSOLForUSDC = spendableSOL - targetSOLRaw
		}
		if availableSOLForUSDC == 0 {
			plan.Status = "funding_path_unavailable"
			plan.Blocker = "no_spare_sol_to_fund_usdc_leg"
			return plan, nil
		}
		prefund, err := estimateSolanaFundingPlan(ctx, cfg, wallet, solanaUSDCAddress, strconv.FormatUint(targetUSDCRaw, 10), slippageBPS, maxPriorityLamports, reserveLamports+targetSOLRaw, quotes)
		if err != nil {
			return solanaLPFundingPlan{}, err
		}
		plan.Prefund = prefund
		plan.Status = prefund.Status
		plan.Blocker = prefund.Blocker
		return plan, nil
	}

	if spendableSOL < targetSOLRaw {
		if snapshot.USDCBalanceRaw <= targetUSDCRaw {
			plan.Status = "funding_path_unavailable"
			plan.Blocker = "no_spare_usdc_to_fund_sol_leg"
			return plan, nil
		}
		requiredSOLShortfall := targetSOLRaw - spendableSOL
		prefund, err := estimateSolanaFundingPlan(ctx, cfg, wallet, solanaWrappedSOLAddress, strconv.FormatUint(requiredSOLShortfall, 10), slippageBPS, maxPriorityLamports, reserveLamports, quotes)
		if err != nil {
			return solanaLPFundingPlan{}, err
		}
		plan.Prefund = prefund
		plan.Status = prefund.Status
		plan.Blocker = prefund.Blocker
		return plan, nil
	}

	plan.Status = "ready_direct"
	return plan, nil
}

func printSolanaLPFundingPlan(plan solanaLPFundingPlan) {
	fmt.Printf("solana_lp_funding_plan wallet=%s chain=solana same_chain_only=true token0=%s token1=%s target_total_usd=%s target_token0_raw=%d target_token1_raw=%d status=%s reserve_sol_lamports=%d\n",
		shortAddress(plan.Wallet),
		shortAddress(plan.Token0),
		shortAddress(plan.Token1),
		plan.TargetTotalUSD.StringFixed(6),
		plan.TargetToken0Raw,
		plan.TargetToken1Raw,
		plan.Status,
		plan.ReservedSOLLamports,
	)
	fmt.Printf("solana_lp_funding_balances sol_raw=%d usdc_raw=%d sol_price_usdc=%s chain_value_usdc=%s\n",
		plan.SOLBalanceRaw,
		plan.USDCBalanceRaw,
		plan.EstimatedSOLPriceUSDC.StringFixed(6),
		plan.EstimatedChainValueUSDC.StringFixed(6),
	)
	if plan.Blocker != "" {
		fmt.Printf("solana_lp_funding_blocker reason=%q\n", plan.Blocker)
	}
	if plan.Prefund.Status != "" {
		printSolanaFundingPlan(plan.Prefund)
	}
}

func printSolanaLPPreflight(result solanaLPPreflight) {
	lpReady := strings.TrimSpace(result.Blocker) == ""
	fmt.Printf("solana_lp_preflight funding_ready=%t prefund_swap_build_ready=%t prefund_swap_sign_ready=%t post_prefund_balance_ready=%t lp_build_ready=%t lp_sign_ready=%t lp_sim_ready=%t sequenced_path_ready=%t lp_execution_path_ready=%t",
		result.FundingReady,
		result.PrefundSwapBuildReady,
		result.PrefundSwapSignReady,
		result.PostPrefundBalanceReady,
		result.LPBuildReady,
		result.LPSignReady,
		result.LPSimReady,
		result.SequencedPathReady,
		lpReady,
	)
	if strings.TrimSpace(result.PoolID) != "" {
		fmt.Printf(" pool_id=%s protocol=%s", result.PoolID, result.PoolProtocol)
	}
	if strings.TrimSpace(result.PreferredPoolID) != "" {
		fmt.Printf(" preferred_pool_id=%s preferred_protocol=%s", result.PreferredPoolID, result.PreferredProtocol)
	}
	if result.LPBuildBase64Len > 0 {
		fmt.Printf(" lp_tx_base64_len=%d", result.LPBuildBase64Len)
	}
	if strings.TrimSpace(result.PositionNFTMint) != "" {
		fmt.Printf(" nft_mint=%s", shortAddress(result.PositionNFTMint))
	}
	if strings.TrimSpace(result.LPSignature) != "" {
		fmt.Printf(" lp_signature=%s", shortAddress(result.LPSignature))
	}
	if result.LPSimUnits > 0 {
		fmt.Printf(" lp_sim_units=%d", result.LPSimUnits)
	}
	if strings.TrimSpace(result.LPSimErr) != "" {
		fmt.Printf(" lp_sim_err=%q", result.LPSimErr)
	}
	if strings.TrimSpace(result.Blocker) != "" {
		fmt.Printf(" blocker=%q", result.Blocker)
	}
	fmt.Println()
	if strings.TrimSpace(result.ExistingPositionID) != "" {
		fmt.Printf("solana_lp_existing_position id=%s status=%s\n", shortAddress(result.ExistingPositionID), result.ExistingPositionStatus)
	}
	if !result.RangeSummary.CurrentPrice.IsZero() {
		fmt.Printf("solana_lp_range current_tick=%d tick_lower=%d tick_upper=%d current_price=%s lower_price=%s upper_price=%s width_bps=%s distance_lower_bps=%s distance_upper_bps=%s occupancy_factor=%s boundary_warning_bps=%s in_range=%t\n",
			result.RangeSummary.CurrentTick,
			result.RangeSummary.TickLower,
			result.RangeSummary.TickUpper,
			result.RangeSummary.CurrentPrice.StringFixed(8),
			result.RangeSummary.LowerPrice.StringFixed(8),
			result.RangeSummary.UpperPrice.StringFixed(8),
			result.RangeSummary.WidthBPS.StringFixed(2),
			result.RangeSummary.DistanceLowerBPS.StringFixed(2),
			result.RangeSummary.DistanceUpperBPS.StringFixed(2),
			result.RangeSummary.OccupancyFactor.StringFixed(4),
			result.RangeSummary.BoundaryWarningBPS.StringFixed(2),
			result.RangeSummary.InRange,
		)
	}
	if !result.FeeProjection.PositionValueUSD.IsZero() {
		fmt.Printf("solana_lp_fee_projection fee_bps=%d pool_tvl_usd=%s pool_vol24h_usd=%s position_usd=%s share_pct=%s estimated_fee_24h_usd=%s estimated_apr=%s\n",
			result.FeeProjection.FeeBPS,
			result.FeeProjection.PoolTVLUSD.StringFixed(2),
			result.FeeProjection.PoolVol24hUSD.StringFixed(2),
			result.FeeProjection.PositionValueUSD.StringFixed(2),
			result.FeeProjection.EstimatedSharePct.StringFixed(4),
			result.FeeProjection.EstimatedFee24hUSD.StringFixed(6),
			result.FeeProjection.EstimatedAPR.StringFixed(2),
		)
	}
	fmt.Printf("solana_lp_exit_signal action=%s reason=%s near_boundary=%t out_of_range=%t expected_close_cost_usd=%s expected_net_edge_24h_usd=%s\n",
		result.ExitSignal.Action,
		result.ExitSignal.Reason,
		result.ExitSignal.NearBoundary,
		result.ExitSignal.OutOfRange,
		result.ExitSignal.ExpectedCloseCostUSD.StringFixed(6),
		result.ExitSignal.ExpectedNetEdge24hUSD.StringFixed(6),
	)
}

func buildPancakeSolanaOpenPositionTransaction(ctx context.Context, cfg *config.Config, poolID string, plan solanaLPFundingPlan) (pancakeswapSolanaOpenPositionBuild, error) {
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	poolPubkey, err := solanago.PublicKeyFromBase58(strings.TrimSpace(poolID))
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("parse pancake pool id: %w", err)
	}
	poolState, err := fetchPancakeSolanaPoolState(ctx, client, poolPubkey)
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, err
	}
	if err := validatePancakeSolanaRewardAccounts(ctx, client, poolState); err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("pancake solana pool reward state invalid: %w", err)
	}
	tickLower64, tickUpper64 := defaultOpenRange(int(poolState.CurrentTick), int64(poolState.TickSpacing))
	tickLower := int32(tickLower64)
	tickUpper := int32(tickUpper64)
	amount0Max, amount1Max, baseFlag, err := solanaLPAmountsForPool(poolState, plan)
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, err
	}
	walletPubkey, err := solanago.PublicKeyFromBase58(strings.TrimSpace(plan.Wallet))
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("parse solana wallet pubkey: %w", err)
	}
	positionNFT := solanago.NewWallet()
	instructions, wrapSOLRequired, err := buildPancakeSolanaOpenPositionInstructions(ctx, client, walletPubkey, positionNFT.PrivateKey, poolState, tickLower, tickUpper, amount0Max, amount1Max)
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, err
	}
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentConfirmed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("fetch solana latest blockhash: %w", err)
	}
	tx, err := solanago.NewTransaction(
		instructions,
		blockhashResp.Value.Blockhash,
		solanago.TransactionPayer(walletPubkey),
	)
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("build pancake solana open-position transaction: %w", err)
	}
	txBytes, err := tx.MarshalBinary()
	if err != nil {
		return pancakeswapSolanaOpenPositionBuild{}, fmt.Errorf("marshal pancake solana open-position transaction: %w", err)
	}
	return pancakeswapSolanaOpenPositionBuild{
		Tx:              tx,
		TxBytes:         txBytes,
		TxBase64:        base64.StdEncoding.EncodeToString(txBytes),
		PositionNFT:     positionNFT.PrivateKey,
		PoolState:       poolState,
		TickLower:       tickLower,
		TickUpper:       tickUpper,
		BaseFlag:        baseFlag,
		Amount0Max:      amount0Max,
		Amount1Max:      amount1Max,
		WrapSOLRequired: wrapSOLRequired,
	}, nil
}

func validatePancakeSolanaRewardAccounts(ctx context.Context, client *solrpc.Client, poolState pancakeswapSolanaPoolState) error {
	for _, reward := range poolState.RewardInfos {
		rewardMintInfo, err := client.GetAccountInfo(ctx, reward.TokenMint)
		if err != nil || rewardMintInfo == nil || rewardMintInfo.Value == nil {
			if err == nil {
				err = fmt.Errorf("not found")
			}
			return fmt.Errorf("reward slot %d mint %s unavailable: %w", reward.Index, reward.TokenMint.String(), err)
		}
		rewardVaultInfo, err := client.GetAccountInfo(ctx, reward.TokenVault)
		if err != nil || rewardVaultInfo == nil || rewardVaultInfo.Value == nil {
			if err == nil {
				err = fmt.Errorf("not found")
			}
			return fmt.Errorf("reward slot %d vault %s unavailable: %w", reward.Index, reward.TokenVault.String(), err)
		}
	}
	return nil
}

func signPancakeSolanaOpenPositionTransaction(tx *solanago.Transaction, feePayer solanago.PrivateKey, positionNFT solanago.PrivateKey) (string, error) {
	if tx == nil {
		return "", fmt.Errorf("pancake solana open-position transaction is nil")
	}
	feePayerPub := feePayer.PublicKey()
	positionPub := positionNFT.PublicKey()
	if _, err := tx.Sign(func(publicKey solanago.PublicKey) *solanago.PrivateKey {
		switch {
		case publicKey.Equals(feePayerPub):
			return &feePayer
		case publicKey.Equals(positionPub):
			return &positionNFT
		default:
			return nil
		}
	}); err != nil {
		return "", fmt.Errorf("sign pancake solana open-position transaction: %w", err)
	}
	if err := tx.VerifySignatures(); err != nil {
		return "", fmt.Errorf("verify pancake solana open-position transaction signatures: %w", err)
	}
	if len(tx.Signatures) == 0 {
		return "", fmt.Errorf("pancake solana open-position transaction missing signatures")
	}
	return tx.Signatures[0].String(), nil
}

func buildPancakeSolanaClosePositionTransaction(ctx context.Context, cfg *config.Config, positionID string, poolID string, walletPubkey solanago.PublicKey) (pancakeswapSolanaClosePositionBuild, error) {
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	poolPubkey, err := solanago.PublicKeyFromBase58(strings.TrimSpace(poolID))
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, fmt.Errorf("parse pancake solana close pool id: %w", err)
	}
	poolState, err := fetchPancakeSolanaPoolState(ctx, client, poolPubkey)
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, err
	}
	positionMint, err := solanago.PublicKeyFromBase58(strings.TrimSpace(positionID))
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, fmt.Errorf("parse pancake solana position mint: %w", err)
	}
	instructions, tokenProgram, err := buildPancakeSolanaClosePositionInstructions(ctx, client, walletPubkey, positionMint)
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, err
	}
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentProcessed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return pancakeswapSolanaClosePositionBuild{}, fmt.Errorf("fetch solana latest blockhash: %w", err)
	}
	tx, err := solanago.NewTransaction(
		instructions,
		blockhashResp.Value.Blockhash,
		solanago.TransactionPayer(walletPubkey),
	)
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, fmt.Errorf("build pancake solana close-position transaction: %w", err)
	}
	txBytes, err := tx.MarshalBinary()
	if err != nil {
		return pancakeswapSolanaClosePositionBuild{}, fmt.Errorf("marshal pancake solana close-position transaction: %w", err)
	}
	return pancakeswapSolanaClosePositionBuild{
		Tx:           tx,
		TxBytes:      txBytes,
		TxBase64:     base64.StdEncoding.EncodeToString(txBytes),
		PoolState:    poolState,
		TokenProgram: tokenProgram,
	}, nil
}

func signPancakeSolanaClosePositionTransaction(tx *solanago.Transaction, feePayer solanago.PrivateKey) (string, error) {
	if tx == nil {
		return "", fmt.Errorf("pancake solana close-position transaction is nil")
	}
	feePayerPub := feePayer.PublicKey()
	if _, err := tx.Sign(func(publicKey solanago.PublicKey) *solanago.PrivateKey {
		if publicKey.Equals(feePayerPub) {
			return &feePayer
		}
		return nil
	}); err != nil {
		return "", fmt.Errorf("sign pancake solana close-position transaction: %w", err)
	}
	if err := tx.VerifySignatures(); err != nil {
		return "", fmt.Errorf("verify pancake solana close-position transaction signatures: %w", err)
	}
	if len(tx.Signatures) == 0 {
		return "", fmt.Errorf("pancake solana close-position transaction missing signatures")
	}
	return tx.Signatures[0].String(), nil
}

func buildPancakeSolanaDecreaseLiquidityTransaction(ctx context.Context, cfg *config.Config, positionID string, poolID string, walletPubkey solanago.PublicKey) (pancakeswapSolanaDecreaseLiquidityBuild, error) {
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	poolPubkey, err := solanago.PublicKeyFromBase58(strings.TrimSpace(poolID))
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, fmt.Errorf("parse pancake solana decrease pool id: %w", err)
	}
	poolState, err := fetchPancakeSolanaPoolState(ctx, client, poolPubkey)
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, err
	}
	positionMint, err := solanago.PublicKeyFromBase58(strings.TrimSpace(positionID))
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, fmt.Errorf("parse pancake solana position mint: %w", err)
	}
	personalPositionState, err := fetchPancakeSolanaPersonalPositionState(ctx, client, positionMint)
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, err
	}
	instructions, err := buildPancakeSolanaDecreaseLiquidityInstructions(ctx, client, walletPubkey, poolState, personalPositionState)
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, err
	}
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentProcessed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, fmt.Errorf("fetch solana latest blockhash: %w", err)
	}
	tx, err := solanago.NewTransaction(
		instructions,
		blockhashResp.Value.Blockhash,
		solanago.TransactionPayer(walletPubkey),
	)
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, fmt.Errorf("build pancake solana decrease-liquidity transaction: %w", err)
	}
	txBytes, err := tx.MarshalBinary()
	if err != nil {
		return pancakeswapSolanaDecreaseLiquidityBuild{}, fmt.Errorf("marshal pancake solana decrease-liquidity transaction: %w", err)
	}
	return pancakeswapSolanaDecreaseLiquidityBuild{
		Tx:           tx,
		TxBytes:      txBytes,
		TxBase64:     base64.StdEncoding.EncodeToString(txBytes),
		PoolState:    poolState,
		LiquidityRaw: personalPositionState.LiquidityRaw,
		TickLower:    personalPositionState.TickLower,
		TickUpper:    personalPositionState.TickUpper,
	}, nil
}

func signPancakeSolanaDecreaseLiquidityTransaction(tx *solanago.Transaction, feePayer solanago.PrivateKey) (string, error) {
	if tx == nil {
		return "", fmt.Errorf("pancake solana decrease-liquidity transaction is nil")
	}
	feePayerPub := feePayer.PublicKey()
	if _, err := tx.Sign(func(publicKey solanago.PublicKey) *solanago.PrivateKey {
		if publicKey.Equals(feePayerPub) {
			return &feePayer
		}
		return nil
	}); err != nil {
		return "", fmt.Errorf("sign pancake solana decrease-liquidity transaction: %w", err)
	}
	if err := tx.VerifySignatures(); err != nil {
		return "", fmt.Errorf("verify pancake solana decrease-liquidity transaction signatures: %w", err)
	}
	if len(tx.Signatures) == 0 {
		return "", fmt.Errorf("pancake solana decrease-liquidity transaction missing signatures")
	}
	return tx.Signatures[0].String(), nil
}

func fetchPancakeSolanaPoolState(ctx context.Context, client *solrpc.Client, poolPubkey solanago.PublicKey) (pancakeswapSolanaPoolState, error) {
	info, err := client.GetAccountInfo(ctx, poolPubkey)
	if err != nil {
		return pancakeswapSolanaPoolState{}, fmt.Errorf("fetch pancake solana pool account: %w", err)
	}
	if info == nil || info.Value == nil {
		return pancakeswapSolanaPoolState{}, fmt.Errorf("pancake solana pool account is empty")
	}
	data := info.Value.Data.GetBinary()
	if len(data) < 273 {
		return pancakeswapSolanaPoolState{}, fmt.Errorf("unexpected pancake solana pool account length: %d", len(data))
	}
	ammConfig := solanago.PublicKeyFromBytes(data[9:41])
	tradeFeeBPS, err := fetchPancakeSolanaTradeFeeBPS(ctx, client, ammConfig)
	if err != nil {
		tradeFeeBPS = 0
	}
	rewardInfos := decodePancakeSolanaRewardInfos(data)
	return pancakeswapSolanaPoolState{
		PoolID:        poolPubkey,
		AmmConfig:     ammConfig,
		TokenMint0:    solanago.PublicKeyFromBytes(data[73:105]),
		TokenMint1:    solanago.PublicKeyFromBytes(data[105:137]),
		TokenVault0:   solanago.PublicKeyFromBytes(data[137:169]),
		TokenVault1:   solanago.PublicKeyFromBytes(data[169:201]),
		MintDecimals0: data[233],
		MintDecimals1: data[234],
		TickSpacing:   binary.LittleEndian.Uint16(data[235:237]),
		TradeFeeBPS:   tradeFeeBPS,
		SqrtPriceX64:  binary.LittleEndian.Uint64(data[253:261]),
		CurrentTick:   int32(binary.LittleEndian.Uint32(data[269:273])),
		RewardInfos:   rewardInfos,
	}, nil
}

func decodePancakeSolanaRewardInfos(data []byte) []pancakeswapSolanaRewardInfo {
	const (
		poolRewardInfosOffset = 397
		poolRewardInfoLen     = 169
		poolRewardCount       = 3
		rewardMintOffset      = 57
		rewardVaultOffset     = 89
	)
	rewards := make([]pancakeswapSolanaRewardInfo, 0, poolRewardCount)
	for i := 0; i < poolRewardCount; i++ {
		start := poolRewardInfosOffset + i*poolRewardInfoLen
		end := start + poolRewardInfoLen
		if len(data) < end {
			break
		}
		tokenMint := solanago.PublicKeyFromBytes(data[start+rewardMintOffset : start+rewardMintOffset+32])
		tokenVault := solanago.PublicKeyFromBytes(data[start+rewardVaultOffset : start+rewardVaultOffset+32])
		if tokenMint.IsZero() || tokenVault.IsZero() {
			continue
		}
		rewards = append(rewards, pancakeswapSolanaRewardInfo{
			Index:      i,
			TokenMint:  tokenMint,
			TokenVault: tokenVault,
		})
	}
	return rewards
}

func fetchPancakeSolanaTradeFeeBPS(ctx context.Context, client *solrpc.Client, ammConfig solanago.PublicKey) (uint, error) {
	info, err := client.GetAccountInfo(ctx, ammConfig)
	if err != nil {
		return 0, fmt.Errorf("fetch pancake solana amm config: %w", err)
	}
	if info == nil || info.Value == nil {
		return 0, fmt.Errorf("pancake solana amm config is empty")
	}
	data := info.Value.Data.GetBinary()
	if len(data) < 51 {
		return 0, fmt.Errorf("unexpected pancake solana amm config length: %d", len(data))
	}
	tradeFeeRate := binary.LittleEndian.Uint32(data[47:51])
	return pancakeTradeFeeRateToBPS(tradeFeeRate), nil
}

func pancakeTradeFeeRateToBPS(rate uint32) uint {
	return uint(math.Round(float64(rate) / 100.0))
}

func fetchPancakeSolanaPersonalPositionState(ctx context.Context, client *solrpc.Client, positionMint solanago.PublicKey) (pancakeswapSolanaPersonalPositionState, error) {
	programID := solanago.MustPublicKeyFromBase58(pancakeswapSolanaCLMMProgramID)
	personalPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), positionMint.Bytes()}, programID)
	if err != nil {
		return pancakeswapSolanaPersonalPositionState{}, fmt.Errorf("derive pancake personal position pda: %w", err)
	}
	info, err := client.GetAccountInfo(ctx, personalPosition)
	if err != nil {
		return pancakeswapSolanaPersonalPositionState{}, fmt.Errorf("fetch pancake personal position account: %w", err)
	}
	if info == nil || info.Value == nil {
		return pancakeswapSolanaPersonalPositionState{}, fmt.Errorf("pancake personal position account is empty")
	}
	data := info.Value.Data.GetBinary()
	if len(data) < 97 {
		return pancakeswapSolanaPersonalPositionState{}, fmt.Errorf("unexpected pancake personal position account length: %d", len(data))
	}
	liquidity := pancakeUint128LEString(data[81:97])
	rewardAmounts := make([]uint64, 0, 4)
	const rewardOffset = 145
	const rewardPadding = 64
	const rewardInfoLen = 24
	if len(data) >= rewardOffset+rewardPadding {
		rewardBytes := len(data) - rewardOffset - rewardPadding
		if rewardBytes > 0 {
			rewardCount := rewardBytes / rewardInfoLen
			for i := 0; i < rewardCount; i++ {
				start := rewardOffset + i*rewardInfoLen
				rewardAmounts = append(rewardAmounts, binary.LittleEndian.Uint64(data[start+16:start+24]))
			}
		}
	}
	return pancakeswapSolanaPersonalPositionState{
		NFTMint:           solanago.PublicKeyFromBytes(data[9:41]),
		PoolID:            solanago.PublicKeyFromBytes(data[41:73]),
		TickLower:         int32(binary.LittleEndian.Uint32(data[73:77])),
		TickUpper:         int32(binary.LittleEndian.Uint32(data[77:81])),
		LiquidityRaw:      liquidity,
		TokenFeesOwed0:    binary.LittleEndian.Uint64(data[129:137]),
		TokenFeesOwed1:    binary.LittleEndian.Uint64(data[137:145]),
		RewardAmountsOwed: rewardAmounts,
	}, nil
}

func pancakeUint128LEString(data []byte) string {
	if len(data) < 16 {
		return "0"
	}
	hi := binary.LittleEndian.Uint64(data[8:16])
	lo := binary.LittleEndian.Uint64(data[0:8])
	v := new(big.Int).SetUint64(hi)
	v.Lsh(v, 64)
	v.Or(v, new(big.Int).SetUint64(lo))
	return v.String()
}

func pancakeUint128StringToLE(raw string) ([]byte, bool) {
	v, ok := new(big.Int).SetString(strings.TrimSpace(raw), 10)
	if !ok || v.Sign() < 0 || v.BitLen() > 128 {
		return nil, false
	}
	out := make([]byte, 16)
	tmp := new(big.Int).Set(v)
	mask := big.NewInt(0xff)
	for i := 0; i < 16; i++ {
		out[i] = byte(new(big.Int).And(tmp, mask).Uint64())
		tmp.Rsh(tmp, 8)
	}
	return out, true
}

func solanaPostPrefundBalances(plan solanaLPFundingPlan) (uint64, uint64, bool) {
	postSOL := plan.SOLBalanceRaw
	postUSDC := plan.USDCBalanceRaw
	if plan.Prefund.FundingMint == solanaWrappedSOLAddress {
		if plan.Prefund.FundingAmountInRaw > postSOL {
			return 0, 0, false
		}
		postSOL -= plan.Prefund.FundingAmountInRaw
	}
	postUSDC += plan.Prefund.FundingExpectedOutRaw
	if plan.Prefund.FundingNetworkFeeLamports > postSOL {
		return 0, 0, false
	}
	postSOL -= plan.Prefund.FundingNetworkFeeLamports
	return postSOL, postUSDC, true
}

func solanaLPBudgetRaw(plan solanaLPFundingPlan) (uint64, uint64, bool) {
	postSOL, postUSDC, ok := solanaPostPrefundBalances(plan)
	if !ok {
		return 0, 0, false
	}
	if postSOL <= plan.ReservedSOLLamports {
		return 0, 0, false
	}
	solBudget := plan.TargetToken0Raw
	usdcBudget := plan.TargetToken1Raw
	if postUSDC > usdcBudget {
		usdcBudget = postUSDC
	}
	return solBudget, usdcBudget, true
}

func solanaLPAmountsForPool(state pancakeswapSolanaPoolState, plan solanaLPFundingPlan) (uint64, uint64, bool, error) {
	if _, _, ok := solanaLPBudgetRaw(plan); !ok {
		return 0, 0, false, fmt.Errorf("solana post-prefund lp budget is unavailable")
	}
	solTarget := float64(plan.TargetToken0Raw) / solanaSOLDecimals
	usdcTarget := float64(plan.TargetToken1Raw) / solanaUSDCDecimals
	switch {
	case state.TokenMint0.String() == solanaWrappedSOLAddress && state.TokenMint1.String() == solanaUSDCAddress:
		amount0Max, amount1Max, baseFlag, err := quotePancakeSolanaOpenPositionAmounts(state, solTarget, usdcTarget)
		if err != nil {
			return 0, 0, false, err
		}
		postSOL, postUSDC, ok := solanaPostPrefundBalances(plan)
		if !ok || postSOL <= plan.ReservedSOLLamports {
			return 0, 0, false, fmt.Errorf("solana post-prefund balances unavailable for lp quote")
		}
		availableSOL := postSOL - plan.ReservedSOLLamports
		if availableSOL < amount0Max {
			return 0, 0, false, fmt.Errorf("solana lp available token0 raw %d is below quoted token0 max %d", availableSOL, amount0Max)
		}
		if postUSDC < amount1Max {
			return 0, 0, false, fmt.Errorf("solana lp available token1 raw %d is below quoted token1 max %d", postUSDC, amount1Max)
		}
		amount1Max = postUSDC
		return amount0Max, amount1Max, baseFlag, nil
	case state.TokenMint0.String() == solanaUSDCAddress && state.TokenMint1.String() == solanaWrappedSOLAddress:
		amount0Max, amount1Max, baseFlag, err := quotePancakeSolanaOpenPositionAmounts(state, usdcTarget, solTarget)
		if err != nil {
			return 0, 0, false, err
		}
		postSOL, postUSDC, ok := solanaPostPrefundBalances(plan)
		if !ok || postSOL <= plan.ReservedSOLLamports {
			return 0, 0, false, fmt.Errorf("solana post-prefund balances unavailable for lp quote")
		}
		availableSOL := postSOL - plan.ReservedSOLLamports
		if postUSDC < amount0Max {
			return 0, 0, false, fmt.Errorf("solana lp available token0 raw %d is below quoted token0 max %d", postUSDC, amount0Max)
		}
		if availableSOL < amount1Max {
			return 0, 0, false, fmt.Errorf("solana lp available token1 raw %d is below quoted token1 max %d", availableSOL, amount1Max)
		}
		amount0Max = postUSDC
		return amount0Max, amount1Max, baseFlag, nil
	default:
		return 0, 0, false, fmt.Errorf("unsupported pancake solana pool mint pair token0=%s token1=%s", state.TokenMint0.String(), state.TokenMint1.String())
	}
}

func buildPancakeSolanaOpenPositionInstructions(ctx context.Context, client *solrpc.Client, walletPubkey solanago.PublicKey, positionNFT solanago.PrivateKey, poolState pancakeswapSolanaPoolState, tickLower int32, tickUpper int32, amount0Max uint64, amount1Max uint64) ([]solanago.Instruction, bool, error) {
	programID := solanago.MustPublicKeyFromBase58(pancakeswapSolanaCLMMProgramID)
	tickLowerStart := pancakeTickArrayStartIndexFromTick(tickLower, poolState.TickSpacing)
	tickUpperStart := pancakeTickArrayStartIndexFromTick(tickUpper, poolState.TickSpacing)
	tickLowerBuf := pancakeInt32BESlice(tickLower)
	tickUpperBuf := pancakeInt32BESlice(tickUpper)
	tickLowerStartBuf := pancakeInt32BESlice(tickLowerStart)
	tickUpperStartBuf := pancakeInt32BESlice(tickUpperStart)
	protocolPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), poolState.PoolID.Bytes(), tickLowerBuf, tickUpperBuf}, programID)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake protocol position pda: %w", err)
	}
	tickArrayLower, _, err := solanago.FindProgramAddress([][]byte{[]byte("tick_array"), poolState.PoolID.Bytes(), tickLowerStartBuf}, programID)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake lower tick array pda: %w", err)
	}
	tickArrayUpper, _, err := solanago.FindProgramAddress([][]byte{[]byte("tick_array"), poolState.PoolID.Bytes(), tickUpperStartBuf}, programID)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake upper tick array pda: %w", err)
	}
	personalPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), positionNFT.PublicKey().Bytes()}, programID)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake personal position pda: %w", err)
	}
	tokenProgram0, err := detectSolanaTokenProgram(ctx, client, poolState.TokenMint0)
	if err != nil {
		return nil, false, err
	}
	tokenProgram1, err := detectSolanaTokenProgram(ctx, client, poolState.TokenMint1)
	if err != nil {
		return nil, false, err
	}
	tokenAccount0, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, poolState.TokenMint0, tokenProgram0)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake token account 0: %w", err)
	}
	tokenAccount1, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, poolState.TokenMint1, tokenProgram1)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake token account 1: %w", err)
	}
	positionNFTAccount, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, positionNFT.PublicKey(), solanago.Token2022ProgramID)
	if err != nil {
		return nil, false, fmt.Errorf("derive pancake position nft ata: %w", err)
	}
	instructions := make([]solanago.Instruction, 0, 8)
	wrapSOLRequired := false
	if err := appendPancakeUserTokenSetupInstructions(ctx, client, &instructions, walletPubkey, poolState.TokenMint0, tokenProgram0, tokenAccount0, amount0Max, &wrapSOLRequired); err != nil {
		return nil, false, err
	}
	if err := appendPancakeUserTokenSetupInstructions(ctx, client, &instructions, walletPubkey, poolState.TokenMint1, tokenProgram1, tokenAccount1, amount1Max, &wrapSOLRequired); err != nil {
		return nil, false, err
	}
	instructionData := encodePancakeOpenPositionData(tickLower, tickUpper, tickLowerStart, tickUpperStart, amount0Max, amount1Max, true)
	instructions = append(instructions, solanago.NewInstruction(
		programID,
		[]*solanago.AccountMeta{
			solanago.Meta(walletPubkey).WRITE().SIGNER(),
			solanago.Meta(walletPubkey),
			solanago.Meta(positionNFT.PublicKey()).WRITE().SIGNER(),
			solanago.Meta(positionNFTAccount).WRITE(),
			solanago.Meta(poolState.PoolID).WRITE(),
			solanago.Meta(protocolPosition).WRITE(),
			solanago.Meta(tickArrayLower).WRITE(),
			solanago.Meta(tickArrayUpper).WRITE(),
			solanago.Meta(personalPosition).WRITE(),
			solanago.Meta(tokenAccount0).WRITE(),
			solanago.Meta(tokenAccount1).WRITE(),
			solanago.Meta(poolState.TokenVault0).WRITE(),
			solanago.Meta(poolState.TokenVault1).WRITE(),
			solanago.Meta(solanago.SysVarRentPubkey),
			solanago.Meta(solanago.SystemProgramID),
			solanago.Meta(solanago.TokenProgramID),
			solanago.Meta(solanago.SPLAssociatedTokenAccountProgramID),
			solanago.Meta(solanago.Token2022ProgramID),
			solanago.Meta(poolState.TokenMint0),
			solanago.Meta(poolState.TokenMint1),
		},
		instructionData,
	))
	return instructions, wrapSOLRequired, nil
}

func buildPancakeSolanaClosePositionInstructions(ctx context.Context, client *solrpc.Client, walletPubkey, positionMint solanago.PublicKey) ([]solanago.Instruction, solanago.PublicKey, error) {
	programID := solanago.MustPublicKeyFromBase58(pancakeswapSolanaCLMMProgramID)
	personalPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), positionMint.Bytes()}, programID)
	if err != nil {
		return nil, solanago.PublicKey{}, fmt.Errorf("derive pancake personal position pda: %w", err)
	}
	tokenProgram, err := detectSolanaTokenProgram(ctx, client, positionMint)
	if err != nil {
		return nil, solanago.PublicKey{}, err
	}
	positionNFTAccount, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, positionMint, tokenProgram)
	if err != nil {
		return nil, solanago.PublicKey{}, fmt.Errorf("derive pancake close position nft ata: %w", err)
	}
	instructionData := make([]byte, 0, len(pancakeClosePositionDiscriminator))
	instructionData = append(instructionData, pancakeClosePositionDiscriminator...)
	instructions := []solanago.Instruction{
		solanago.NewInstruction(
			programID,
			[]*solanago.AccountMeta{
				solanago.Meta(walletPubkey).WRITE().SIGNER(),
				solanago.Meta(positionMint).WRITE(),
				solanago.Meta(positionNFTAccount).WRITE(),
				solanago.Meta(personalPosition).WRITE(),
				solanago.Meta(solanago.SystemProgramID),
				solanago.Meta(tokenProgram),
			},
			instructionData,
		),
	}
	return instructions, tokenProgram, nil
}

func buildPancakeSolanaDecreaseLiquidityInstructions(ctx context.Context, client *solrpc.Client, walletPubkey solanago.PublicKey, poolState pancakeswapSolanaPoolState, personal pancakeswapSolanaPersonalPositionState) ([]solanago.Instruction, error) {
	programID := solanago.MustPublicKeyFromBase58(pancakeswapSolanaCLMMProgramID)
	positionMint := personal.NFTMint
	tokenProgramPosition, err := detectSolanaTokenProgram(ctx, client, positionMint)
	if err != nil {
		return nil, err
	}
	positionNFTAccount, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, positionMint, tokenProgramPosition)
	if err != nil {
		return nil, fmt.Errorf("derive pancake decrease position nft ata: %w", err)
	}
	personalPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), positionMint.Bytes()}, programID)
	if err != nil {
		return nil, fmt.Errorf("derive pancake personal position pda: %w", err)
	}
	tickLowerBuf := pancakeInt32BESlice(personal.TickLower)
	tickUpperBuf := pancakeInt32BESlice(personal.TickUpper)
	protocolPosition, _, err := solanago.FindProgramAddress([][]byte{[]byte("position"), poolState.PoolID.Bytes(), tickLowerBuf, tickUpperBuf}, programID)
	if err != nil {
		return nil, fmt.Errorf("derive pancake protocol position pda: %w", err)
	}
	tickLowerStart := pancakeTickArrayStartIndexFromTick(personal.TickLower, poolState.TickSpacing)
	tickUpperStart := pancakeTickArrayStartIndexFromTick(personal.TickUpper, poolState.TickSpacing)
	tickLowerStartBuf := pancakeInt32BESlice(tickLowerStart)
	tickUpperStartBuf := pancakeInt32BESlice(tickUpperStart)
	tickArrayLower, _, err := solanago.FindProgramAddress([][]byte{[]byte("tick_array"), poolState.PoolID.Bytes(), tickLowerStartBuf}, programID)
	if err != nil {
		return nil, fmt.Errorf("derive pancake lower tick array pda: %w", err)
	}
	tickArrayUpper, _, err := solanago.FindProgramAddress([][]byte{[]byte("tick_array"), poolState.PoolID.Bytes(), tickUpperStartBuf}, programID)
	if err != nil {
		return nil, fmt.Errorf("derive pancake upper tick array pda: %w", err)
	}
	tokenProgram0, err := detectSolanaTokenProgram(ctx, client, poolState.TokenMint0)
	if err != nil {
		return nil, err
	}
	tokenProgram1, err := detectSolanaTokenProgram(ctx, client, poolState.TokenMint1)
	if err != nil {
		return nil, err
	}
	recipientTokenAccount0, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, poolState.TokenMint0, tokenProgram0)
	if err != nil {
		return nil, fmt.Errorf("derive pancake decrease recipient token account 0: %w", err)
	}
	recipientTokenAccount1, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, poolState.TokenMint1, tokenProgram1)
	if err != nil {
		return nil, fmt.Errorf("derive pancake decrease recipient token account 1: %w", err)
	}
	instructions := make([]solanago.Instruction, 0, 4)
	if err := appendPancakeEnsureTokenAccountInstruction(ctx, client, &instructions, walletPubkey, poolState.TokenMint0, tokenProgram0, recipientTokenAccount0); err != nil {
		return nil, err
	}
	if err := appendPancakeEnsureTokenAccountInstruction(ctx, client, &instructions, walletPubkey, poolState.TokenMint1, tokenProgram1, recipientTokenAccount1); err != nil {
		return nil, err
	}
	if err := validatePancakeSolanaRewardAccounts(ctx, client, poolState); err != nil {
		return nil, fmt.Errorf("pancake reward accounts invalid: %w", err)
	}
	rewardAccounts := make([]*solanago.AccountMeta, 0, len(poolState.RewardInfos)*3)
	for _, reward := range poolState.RewardInfos {
		rewardTokenProgram, err := detectSolanaTokenProgram(ctx, client, reward.TokenMint)
		if err != nil {
			return nil, err
		}
		recipientRewardTokenAccount, _, err := solanago.FindAssociatedTokenAddressWithProgram(walletPubkey, reward.TokenMint, rewardTokenProgram)
		if err != nil {
			return nil, fmt.Errorf("derive pancake decrease reward recipient token account for %s: %w", reward.TokenMint.String(), err)
		}
		if err := appendPancakeEnsureTokenAccountInstruction(ctx, client, &instructions, walletPubkey, reward.TokenMint, rewardTokenProgram, recipientRewardTokenAccount); err != nil {
			return nil, err
		}
		rewardAccounts = append(rewardAccounts,
			solanago.Meta(reward.TokenVault).WRITE(),
			solanago.Meta(recipientRewardTokenAccount).WRITE(),
			solanago.Meta(reward.TokenMint),
		)
	}
	liquidityBytes, ok := pancakeUint128StringToLE(personal.LiquidityRaw)
	if !ok {
		return nil, fmt.Errorf("invalid pancake liquidity raw %q", personal.LiquidityRaw)
	}
	data := make([]byte, 0, 8+16+8+8)
	data = append(data, pancakeDecreaseLiquidityV2Discriminator...)
	data = append(data, liquidityBytes...)
	data = appendUint64LE(data, 0)
	data = appendUint64LE(data, 0)
	accounts := []*solanago.AccountMeta{
		solanago.Meta(walletPubkey).WRITE().SIGNER(),
		solanago.Meta(positionNFTAccount).WRITE(),
		solanago.Meta(personalPosition).WRITE(),
		solanago.Meta(poolState.PoolID).WRITE(),
		solanago.Meta(protocolPosition).WRITE(),
		solanago.Meta(poolState.TokenVault0).WRITE(),
		solanago.Meta(poolState.TokenVault1).WRITE(),
		solanago.Meta(tickArrayLower).WRITE(),
		solanago.Meta(tickArrayUpper).WRITE(),
		solanago.Meta(recipientTokenAccount0).WRITE(),
		solanago.Meta(recipientTokenAccount1).WRITE(),
		solanago.Meta(solanago.TokenProgramID),
		solanago.Meta(solanago.Token2022ProgramID),
		solanago.Meta(solanago.MustPublicKeyFromBase58(solanaMemoProgramID)),
		solanago.Meta(poolState.TokenMint0),
		solanago.Meta(poolState.TokenMint1),
	}
	accounts = append(accounts, rewardAccounts...)
	instructions = append(instructions, solanago.NewInstruction(programID, accounts, data))
	return instructions, nil
}

func appendPancakeEnsureTokenAccountInstruction(ctx context.Context, client *solrpc.Client, instructions *[]solanago.Instruction, walletPubkey, mint, tokenProgram, tokenAccount solanago.PublicKey) error {
	_, err := client.GetAccountInfo(ctx, tokenAccount)
	accountExists := err == nil
	if err != nil && !errors.Is(err, solrpc.ErrNotFound) {
		return fmt.Errorf("lookup pancake ensure token account %s: %w", tokenAccount.String(), err)
	}
	if !accountExists {
		createIx, buildErr := ata.NewCreateIdempotentInstructionWithTokenProgram(walletPubkey, walletPubkey, mint, tokenProgram).ValidateAndBuild()
		if buildErr != nil {
			return fmt.Errorf("build pancake create ata for %s: %w", mint.String(), buildErr)
		}
		*instructions = append(*instructions, createIx)
	}
	return nil
}

func appendPancakeUserTokenSetupInstructions(ctx context.Context, client *solrpc.Client, instructions *[]solanago.Instruction, walletPubkey, mint, tokenProgram, tokenAccount solanago.PublicKey, amount uint64, wrapSOLRequired *bool) error {
	_, err := client.GetAccountInfo(ctx, tokenAccount)
	accountExists := err == nil
	if err != nil && !errors.Is(err, solrpc.ErrNotFound) {
		return fmt.Errorf("lookup pancake user token account %s: %w", tokenAccount.String(), err)
	}
	if !accountExists {
		createIx, buildErr := ata.NewCreateIdempotentInstructionWithTokenProgram(walletPubkey, walletPubkey, mint, tokenProgram).ValidateAndBuild()
		if buildErr != nil {
			return fmt.Errorf("build pancake create ata for %s: %w", mint.String(), buildErr)
		}
		*instructions = append(*instructions, createIx)
	}
	if mint.Equals(solanago.WrappedSol) {
		*wrapSOLRequired = true
		if amount > 0 {
			*instructions = append(*instructions, systemprog.NewTransferInstruction(amount, walletPubkey, tokenAccount).Build())
			syncIx, buildErr := tokenprog.NewSyncNativeInstruction(tokenAccount).ValidateAndBuild()
			if buildErr != nil {
				return fmt.Errorf("build pancake sync native for %s: %w", tokenAccount.String(), buildErr)
			}
			*instructions = append(*instructions, syncIx)
		}
	}
	return nil
}

func detectSolanaTokenProgram(ctx context.Context, client *solrpc.Client, mint solanago.PublicKey) (solanago.PublicKey, error) {
	info, err := client.GetAccountInfo(ctx, mint)
	if err != nil {
		return solanago.PublicKey{}, fmt.Errorf("fetch solana mint account %s: %w", mint.String(), err)
	}
	if info == nil || info.Value == nil {
		return solanago.TokenProgramID, nil
	}
	if info.Value.Owner.Equals(solanago.Token2022ProgramID) {
		return solanago.Token2022ProgramID, nil
	}
	return solanago.TokenProgramID, nil
}

func pancakeTickArrayStartIndexFromTick(tick int32, tickSpacing uint16) int32 {
	spacing := int32(tickSpacing)
	if spacing <= 0 {
		spacing = 1
	}
	ticksPerArray := spacing * 60
	quotient := int64(tick) / int64(ticksPerArray)
	remainder := int64(tick) % int64(ticksPerArray)
	if remainder != 0 && tick < 0 {
		quotient--
	}
	return int32(quotient) * ticksPerArray
}

func pancakeInt32BESlice(value int32) []byte {
	buf := make([]byte, 4)
	binary.BigEndian.PutUint32(buf, uint32(value))
	return buf
}

func encodePancakeOpenPositionData(tickLower int32, tickUpper int32, lowerStart int32, upperStart int32, amount0Max uint64, amount1Max uint64, baseFlag bool) []byte {
	data := make([]byte, 0, 8+4+4+4+4+16+8+8+1+2)
	data = append(data, pancakeOpenPositionWithToken22NftDiscriminator...)
	data = appendInt32LE(data, tickLower)
	data = appendInt32LE(data, tickUpper)
	data = appendInt32LE(data, lowerStart)
	data = appendInt32LE(data, upperStart)
	data = append(data, make([]byte, 16)...)
	data = appendUint64LE(data, amount0Max)
	data = appendUint64LE(data, amount1Max)
	data = append(data, byte(0))
	data = append(data, byte(1))
	if baseFlag {
		data = append(data, byte(1))
	} else {
		data = append(data, byte(0))
	}
	return data
}

func quotePancakeSolanaOpenPositionAmounts(state pancakeswapSolanaPoolState, amount0Target float64, amount1Target float64) (uint64, uint64, bool, error) {
	if amount0Target <= 0 && amount1Target <= 0 {
		return 0, 0, false, fmt.Errorf("pancake solana quote requires non-zero target amounts")
	}
	tickLower64, tickUpper64 := defaultOpenRange(int(state.CurrentTick), int64(state.TickSpacing))
	currentPrice := pancakeSqrtPriceX64ToPrice(state.SqrtPriceX64, int(state.MintDecimals0)-int(state.MintDecimals1))
	lowerPrice := pancakeTickToPrice(int(tickLower64), int(state.MintDecimals0)-int(state.MintDecimals1))
	upperPrice := pancakeTickToPrice(int(tickUpper64), int(state.MintDecimals0)-int(state.MintDecimals1))
	liquidityFromBase := pancakeLiquidityFromSingleAmount(currentPrice, lowerPrice, upperPrice, amount0Target, true, int(state.MintDecimals0), int(state.MintDecimals1))
	liquidityFromQuote := pancakeLiquidityFromSingleAmount(currentPrice, lowerPrice, upperPrice, amount1Target, false, int(state.MintDecimals0), int(state.MintDecimals1))
	baseLimited := liquidityFromBase <= liquidityFromQuote
	liquidity := liquidityFromQuote
	if baseLimited {
		liquidity = liquidityFromBase
	}
	if liquidity <= 0 {
		return 0, 0, baseLimited, fmt.Errorf("pancake solana derived liquidity is zero")
	}
	amount0, amount1 := pancakeAmountsFromLiquidity(currentPrice, lowerPrice, upperPrice, liquidity, int(state.MintDecimals0), int(state.MintDecimals1))
	slippageMultiplier := 1.01
	amount0Max := uint64(math.Ceil(amount0 * slippageMultiplier * math.Pow10(int(state.MintDecimals0))))
	amount1Max := uint64(math.Ceil(amount1 * slippageMultiplier * math.Pow10(int(state.MintDecimals1))))
	if amount0Max == 0 && amount1Max == 0 {
		return 0, 0, baseLimited, fmt.Errorf("pancake solana quoted amounts are both zero")
	}
	return amount0Max, amount1Max, baseLimited, nil
}

func pancakeSqrtPriceX64ToPrice(sqrtPriceX64 uint64, decimalDiff int) float64 {
	sqrtPrice := float64(sqrtPriceX64) / math.Pow(2, 64)
	return sqrtPrice * sqrtPrice * math.Pow10(decimalDiff)
}

func pancakeTickToPrice(tick int, decimalDiff int) float64 {
	return math.Pow(1.0001, float64(tick)) * math.Pow10(decimalDiff)
}

func pancakeLiquidityFromSingleAmount(currentPrice, lowerPrice, upperPrice, amount float64, isToken0 bool, decimals0, decimals1 int) float64 {
	decimalScale := math.Pow10(decimals0 - decimals1)
	sqrtCurrent := math.Sqrt(currentPrice / decimalScale)
	sqrtLower := math.Sqrt(lowerPrice / decimalScale)
	sqrtUpper := math.Sqrt(upperPrice / decimalScale)
	if isToken0 {
		amountRaw := amount * math.Pow10(decimals0)
		if currentPrice >= upperPrice {
			return (amountRaw * sqrtLower * sqrtUpper) / (sqrtUpper - sqrtLower)
		}
		if currentPrice < lowerPrice {
			return 0
		}
		return (amountRaw * sqrtCurrent * sqrtUpper) / (sqrtUpper - sqrtCurrent)
	}
	amountRaw := amount * math.Pow10(decimals1)
	if currentPrice < lowerPrice {
		return amountRaw / (sqrtUpper - sqrtLower)
	}
	if currentPrice >= upperPrice {
		return 0
	}
	return amountRaw / (sqrtCurrent - sqrtLower)
}

func pancakeAmountsFromLiquidity(currentPrice, lowerPrice, upperPrice, liquidity float64, decimals0, decimals1 int) (float64, float64) {
	decimalScale := math.Pow10(decimals0 - decimals1)
	sqrtCurrent := math.Sqrt(currentPrice / decimalScale)
	sqrtLower := math.Sqrt(lowerPrice / decimalScale)
	sqrtUpper := math.Sqrt(upperPrice / decimalScale)
	var amount0Raw float64
	var amount1Raw float64
	switch {
	case currentPrice < lowerPrice:
		amount0Raw = 0
		amount1Raw = liquidity * (sqrtUpper - sqrtLower)
	case currentPrice >= upperPrice:
		amount0Raw = (liquidity * (sqrtUpper - sqrtLower)) / (sqrtLower * sqrtUpper)
		amount1Raw = 0
	default:
		amount0Raw = (liquidity * (sqrtUpper - sqrtCurrent)) / (sqrtCurrent * sqrtUpper)
		amount1Raw = liquidity * (sqrtCurrent - sqrtLower)
	}
	return amount0Raw / math.Pow10(decimals0), amount1Raw / math.Pow10(decimals1)
}

func appendInt32LE(dst []byte, value int32) []byte {
	buf := make([]byte, 4)
	binary.LittleEndian.PutUint32(buf, uint32(value))
	return append(dst, buf...)
}

func appendUint64LE(dst []byte, value uint64) []byte {
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, value)
	return append(dst, buf...)
}

func derefUint64(value *uint64) uint64 {
	if value == nil {
		return 0
	}
	return *value
}

func evaluateSolanaPostPrefundBalances(plan solanaLPFundingPlan, openBuild pancakeswapSolanaOpenPositionBuild) (uint64, uint64, bool) {
	postSOL, postUSDC, ok := solanaPostPrefundBalances(plan)
	if !ok {
		return 0, 0, false
	}
	postSOLNeeded := openBuild.Amount0Max + plan.ReservedSOLLamports
	postUSDCNeeded := openBuild.Amount1Max
	ready := postSOL >= postSOLNeeded && postUSDC >= postUSDCNeeded
	return postSOL, postUSDC, ready
}

func resolveSolanaSwapUserPublicKey(userPublicKey string) (string, error) {
	userPublicKey = strings.TrimSpace(userPublicKey)
	if userPublicKey == "" {
		userPublicKey = strings.TrimSpace(os.Getenv("SOLANA_FEE_PAYER_ADDRESS"))
	}
	if userPublicKey == "" {
		return "", fmt.Errorf("solana user public key is empty; set SOLANA_FEE_PAYER_ADDRESS or pass --solana-swap-user-public-key")
	}
	userAddress, err := domain.ParseAddress(userPublicKey)
	if err != nil {
		return "", fmt.Errorf("invalid solana user public key: %w", err)
	}
	if userAddress.Chain() != domain.ChainSolana {
		return "", fmt.Errorf("solana user public key is not a solana address")
	}
	return userAddress.String(), nil
}

func solanaWalletMintBalance(snapshot solanaWalletSnapshot, mint string) uint64 {
	switch mint {
	case solanaUSDCAddress:
		return snapshot.USDCBalanceRaw
	case solanaWrappedSOLAddress:
		return snapshot.SOLBalanceRaw
	default:
		return 0
	}
}

func findExactInQuoteForTargetOut(ctx context.Context, inputMint string, outputMint string, targetOutRaw uint64, maxInputRaw uint64, slippageBPS int, solPriceUSDC domain.Decimal, quotes *solanaFundingQuoteClient) (jupiterQuoteSummary, uint64, error) {
	if maxInputRaw == 0 || targetOutRaw == 0 {
		return jupiterQuoteSummary{}, 0, fmt.Errorf("insufficient_same_chain_liquidity_or_balance")
	}
	guess := estimateFundingInputRaw(inputMint, outputMint, targetOutRaw, solPriceUSDC)
	if guess == 0 {
		guess = maxInputRaw
	}
	if guess > maxInputRaw {
		guess = maxInputRaw
	}
	if guess == 0 {
		guess = 1
	}
	var lastQuote jupiterQuoteSummary
	var lastErr error
	for attempt := 0; attempt < 5; attempt++ {
		quote, err := quotes.Quote(ctx, inputMint, outputMint, strconv.FormatUint(guess, 10), slippageBPS)
		if err != nil {
			return jupiterQuoteSummary{}, 0, fmt.Errorf("funding quote %s->%s failed: %w", shortAddress(inputMint), shortAddress(outputMint), err)
		}
		lastQuote = quote
		outRaw := mustParseUint64(quote.OutAmount)
		if outRaw >= targetOutRaw {
			bestQuote := quote
			bestInput := guess
			for refine := 0; refine < 3; refine++ {
				bestOut := mustParseUint64(bestQuote.OutAmount)
				if bestOut == 0 {
					break
				}
				scaledInput := domain.NewDecimalFromInt(int64(bestInput)).
					Mul(domain.NewDecimalFromInt(int64(targetOutRaw))).
					Div(domain.NewDecimalFromInt(int64(bestOut))).
					Mul(domain.MustDecimal("1.03")).
					Ceil().
					BigInt().
					Uint64()
				if scaledInput == 0 || scaledInput >= bestInput {
					break
				}
				refinedQuote, err := quotes.Quote(ctx, inputMint, outputMint, strconv.FormatUint(scaledInput, 10), slippageBPS)
				if err != nil {
					break
				}
				refinedOut := mustParseUint64(refinedQuote.OutAmount)
				if refinedOut >= targetOutRaw {
					bestQuote = refinedQuote
					bestInput = scaledInput
				} else {
					break
				}
			}
			low := uint64(1)
			high := bestInput
			for refine := 0; refine < 8 && low < high; refine++ {
				mid := low + (high-low)/2
				if mid == 0 {
					mid = 1
				}
				refinedQuote, err := quotes.Quote(ctx, inputMint, outputMint, strconv.FormatUint(mid, 10), slippageBPS)
				if err != nil {
					break
				}
				refinedOut := mustParseUint64(refinedQuote.OutAmount)
				if refinedOut >= targetOutRaw {
					bestQuote = refinedQuote
					bestInput = mid
					high = mid
				} else {
					low = mid + 1
				}
			}
			return bestQuote, bestInput, nil
		}
		if guess >= maxInputRaw {
			lastErr = fmt.Errorf("insufficient_same_chain_liquidity_or_balance")
			break
		}
		if outRaw == 0 {
			guess = maxInputRaw
			continue
		}
		scale := domain.NewDecimalFromInt(int64(targetOutRaw)).
			Div(domain.NewDecimalFromInt(int64(outRaw))).
			Mul(domain.MustDecimal("1.03"))
		nextGuess := domain.NewDecimalFromInt(int64(guess)).Mul(scale).Ceil().BigInt().Uint64()
		if nextGuess <= guess {
			nextGuess = guess + max(guess/20, 1)
		}
		if nextGuess > maxInputRaw {
			nextGuess = maxInputRaw
		}
		guess = nextGuess
	}
	if lastErr != nil {
		return jupiterQuoteSummary{}, 0, lastErr
	}
	if lastQuote.OutAmount != "" {
		return lastQuote, guess, fmt.Errorf("insufficient_same_chain_liquidity_or_balance")
	}
	return jupiterQuoteSummary{}, 0, fmt.Errorf("insufficient_same_chain_liquidity_or_balance")
}

func fetchSolanaSpotPriceUSDC(ctx context.Context, slippageBPS int, quotes *solanaFundingQuoteClient) (domain.Decimal, error) {
	quote, err := quotes.Quote(ctx, solanaWrappedSOLAddress, solanaUSDCAddress, "10000000", slippageBPS)
	if err != nil {
		return domain.NewDecimalFromInt(0), fmt.Errorf("fetch solana spot price: %w", err)
	}
	outRaw := mustParseUint64(quote.OutAmount)
	if outRaw == 0 {
		return domain.NewDecimalFromInt(0), fmt.Errorf("fetch solana spot price: empty output")
	}
	return rawUSDCToDecimal(outRaw).Div(rawSOLToDecimal(10000000)), nil
}

func rawUSDCToDecimal(raw uint64) domain.Decimal {
	return domain.NewDecimalFromInt(int64(raw)).Div(domain.NewDecimalFromInt(solanaUSDCDecimals))
}

func rawSOLToDecimal(raw uint64) domain.Decimal {
	return domain.NewDecimalFromInt(int64(raw)).Div(domain.NewDecimalFromInt(solanaSOLDecimals))
}

func diffUint64(a uint64, b uint64) uint64 {
	if a >= b {
		return a - b
	}
	return 0
}

func mustParseUint64(value string) uint64 {
	parsed, err := strconv.ParseUint(strings.TrimSpace(value), 10, 64)
	if err != nil {
		return 0
	}
	return parsed
}

func estimateFundingInputRaw(inputMint string, outputMint string, targetOutRaw uint64, solPriceUSDC domain.Decimal) uint64 {
	switch {
	case inputMint == solanaWrappedSOLAddress && outputMint == solanaUSDCAddress:
		targetUSDC := rawUSDCToDecimal(targetOutRaw)
		guessSOL := targetUSDC.Div(solPriceUSDC).Mul(domain.MustDecimal("1.02"))
		return decimalToScaledUint64(guessSOL, solanaSOLDecimals)
	case inputMint == solanaUSDCAddress && outputMint == solanaWrappedSOLAddress:
		targetSOL := rawSOLToDecimal(targetOutRaw)
		guessUSDC := targetSOL.Mul(solPriceUSDC).Mul(domain.MustDecimal("1.02"))
		return decimalToScaledUint64(guessUSDC, solanaUSDCDecimals)
	default:
		return 0
	}
}

func max(a uint64, b uint64) uint64 {
	if a > b {
		return a
	}
	return b
}

func discoverPreferredSolanaLPPool(ctx context.Context) (*ports.PoolDiscovery, error) {
	minTVL := domain.MustDecimal("100000")
	minVol24h := domain.MustDecimal("100000")
	gecko := geckoterminal.NewAdapter()
	fallback := dexscreener.NewAdapter()
	pools, err := gecko.DiscoverPools(ctx, domain.ChainSolana, "", minTVL, 8)
	if err != nil {
		pools, err = fallback.DiscoverPools(ctx, domain.ChainSolana, "", minTVL, 8)
		if err != nil {
			if knownPool, knownErr := fallback.GetPoolMetadata(ctx, domain.ChainSolana, solanaKnownSOLUSDCPool); knownErr == nil && knownPool != nil && knownPool.ID != "" {
				return &ports.PoolDiscovery{
					ID:        knownPool.ID,
					Chain:     knownPool.Chain,
					Protocol:  knownPool.Protocol,
					Token0:    knownPool.Token0,
					Token1:    knownPool.Token1,
					FeeBPS:    knownPool.FeeBPS,
					TVLUSD:    knownPool.TVLUSD,
					Vol24h:    knownPool.Vol24h,
					UpdatedAt: time.Now(),
				}, nil
			}
			return nil, err
		}
	}
	for i := range pools {
		ok, _ := solanaPoolRiskEligible(pools[i], minTVL, minVol24h)
		if ok {
			pool := pools[i]
			return &pool, nil
		}
	}
	if knownPool, knownErr := fallback.GetPoolMetadata(ctx, domain.ChainSolana, solanaKnownSOLUSDCPool); knownErr == nil && knownPool != nil && knownPool.ID != "" {
		return &ports.PoolDiscovery{
			ID:        knownPool.ID,
			Chain:     knownPool.Chain,
			Protocol:  knownPool.Protocol,
			Token0:    knownPool.Token0,
			Token1:    knownPool.Token1,
			FeeBPS:    knownPool.FeeBPS,
			TVLUSD:    knownPool.TVLUSD,
			Vol24h:    knownPool.Vol24h,
			UpdatedAt: time.Now(),
		}, nil
	}
	return nil, nil
}

func discoverPreferredSolanaProtocolPool(ctx context.Context) (*ports.PoolDiscovery, error) {
	minTVL := domain.MustDecimal("100000")
	minVol24h := domain.MustDecimal("100000")
	gecko := geckoterminal.NewAdapter()
	fallback := dexscreener.NewAdapter()
	pools, err := gecko.DiscoverPools(ctx, domain.ChainSolana, "", minTVL, 12)
	if err != nil {
		pools, err = fallback.DiscoverPools(ctx, domain.ChainSolana, "", minTVL, 12)
		if err != nil {
			if knownPool, knownErr := fallback.GetPoolMetadata(ctx, domain.ChainSolana, solanaKnownSOLUSDCPool); knownErr == nil && knownPool != nil && knownPool.ID != "" {
				return &ports.PoolDiscovery{
					ID:        knownPool.ID,
					Chain:     knownPool.Chain,
					Protocol:  knownPool.Protocol,
					Token0:    knownPool.Token0,
					Token1:    knownPool.Token1,
					FeeBPS:    knownPool.FeeBPS,
					TVLUSD:    knownPool.TVLUSD,
					Vol24h:    knownPool.Vol24h,
					UpdatedAt: time.Now(),
				}, nil
			}
			return nil, err
		}
	}
	var best *ports.PoolDiscovery
	for i := range pools {
		if pools[i].Chain != domain.ChainSolana {
			continue
		}
		if !isSolanaPriorityLPPair(pools[i].Token0, pools[i].Token1) {
			continue
		}
		if pools[i].TVLUSD.LessThan(minTVL) || pools[i].Vol24h.LessThan(minVol24h) {
			continue
		}
		if best == nil {
			pool := pools[i]
			best = &pool
			continue
		}
		pi := solanaProtocolPriority(pools[i].Protocol)
		pb := solanaProtocolPriority(best.Protocol)
		if pi < pb || (pi == pb && pools[i].Vol24h.GreaterThan(best.Vol24h)) {
			pool := pools[i]
			best = &pool
		}
	}
	if best == nil {
		if knownPool, knownErr := fallback.GetPoolMetadata(ctx, domain.ChainSolana, solanaKnownSOLUSDCPool); knownErr == nil && knownPool != nil && knownPool.ID != "" {
			return &ports.PoolDiscovery{
				ID:        knownPool.ID,
				Chain:     knownPool.Chain,
				Protocol:  knownPool.Protocol,
				Token0:    knownPool.Token0,
				Token1:    knownPool.Token1,
				FeeBPS:    knownPool.FeeBPS,
				TVLUSD:    knownPool.TVLUSD,
				Vol24h:    knownPool.Vol24h,
				UpdatedAt: time.Now(),
			}, nil
		}
	}
	return best, nil
}

func solanaLPExecutionBlocker(protocol string) string {
	switch strings.ToLower(strings.TrimSpace(protocol)) {
	case "":
		return "solana_lp_protocol_candidate_not_found"
	case "pancakeswap-v3-solana":
		return "solana_pancakeswap_v3_solana_add_liquidity_adapter_not_implemented"
	case "raydium-clmm":
		return "solana_raydium_clmm_add_liquidity_adapter_not_implemented"
	case "orca-whirlpool":
		return "solana_orca_whirlpool_add_liquidity_adapter_not_implemented"
	default:
		return fmt.Sprintf("solana_%s_add_liquidity_adapter_not_implemented", strings.ReplaceAll(strings.ToLower(protocol), "-", "_"))
	}
}

func decimalFromStringStrict(value string) (domain.Decimal, error) {
	raw := strings.TrimSpace(value)
	if raw == "" {
		return domain.ZeroDecimal(), fmt.Errorf("empty decimal string")
	}
	return decimal.NewFromString(raw)
}

func decimalToScaledUint64(value domain.Decimal, scale int64) uint64 {
	scaled := value.Mul(domain.NewDecimalFromInt(scale)).Floor()
	if !scaled.IsPositive() {
		return 0
	}
	return scaled.BigInt().Uint64()
}

func maybeAppendEstimatedFundingLedgerEntries(ctx context.Context, cfg *config.Config, positionID string, swapUSD domain.Decimal, gasUSD domain.Decimal, slippageUSD domain.Decimal) error {
	if positionID == "" {
		return nil
	}
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		return fmt.Errorf("funding ledger append requested for %s but postgres dsn is empty", positionID)
	}
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return fmt.Errorf("open postgres for funding ledger append: %w", err)
	}
	defer store.Close()
	blockRef, err := currentSolanaBlockRef(ctx, cfg)
	if err != nil {
		return err
	}
	if !swapUSD.IsZero() {
		if _, err := store.Append(ctx, ports.LedgerEntry{PositionID: positionID, Kind: ports.LedgerEntrySwap, Amount: swapUSD.Neg(), TokenSymbol: "USDC", BlockRef: blockRef, TxHash: ""}); err != nil {
			return fmt.Errorf("append estimated funding swap ledger entry: %w", err)
		}
	}
	if !gasUSD.IsZero() {
		if _, err := store.Append(ctx, ports.LedgerEntry{PositionID: positionID, Kind: ports.LedgerEntryGas, Amount: gasUSD.Neg(), TokenSymbol: "USDC", BlockRef: blockRef, TxHash: ""}); err != nil {
			return fmt.Errorf("append estimated funding gas ledger entry: %w", err)
		}
	}
	if !slippageUSD.IsZero() {
		if _, err := store.Append(ctx, ports.LedgerEntry{PositionID: positionID, Kind: ports.LedgerEntrySlippage, Amount: slippageUSD.Neg(), TokenSymbol: "USDC", BlockRef: blockRef, TxHash: ""}); err != nil {
			return fmt.Errorf("append estimated funding slippage ledger entry: %w", err)
		}
	}
	fmt.Printf("solana_funding_ledger_appended position_id=%s swap_usdc=%s gas_usdc=%s slippage_usdc=%s tx_hash=estimated_only\n",
		positionID,
		swapUSD.StringFixed(6),
		gasUSD.StringFixed(6),
		slippageUSD.StringFixed(6),
	)
	return nil
}

func currentSolanaBlockRef(ctx context.Context, cfg *config.Config) (domain.BlockRef, error) {
	endpoint := solanaReadinessEndpoint(cfg)
	if endpoint == "" {
		return domain.BlockRef{}, fmt.Errorf("solana rpc endpoint is empty")
	}
	slotRaw, err := solanaJSONRPC(ctx, endpoint, "getSlot", []any{map[string]any{"commitment": "processed"}})
	if err != nil {
		return domain.BlockRef{}, fmt.Errorf("solana funding getSlot: %w", err)
	}
	var slot struct {
		Value uint64
	}
	if err := json.Unmarshal(slotRaw, &slot.Value); err != nil {
		var number uint64
		if err2 := json.Unmarshal(slotRaw, &number); err2 != nil {
			return domain.BlockRef{}, fmt.Errorf("decode solana funding slot: %w", err)
		}
		slot.Value = number
	}
	return domain.BlockRef{Chain: domain.ChainSolana, Number: slot.Value, TimeUnix: time.Now().Unix()}, nil
}

func (c *solanaFundingQuoteClient) Quote(ctx context.Context, inputMint string, outputMint string, amountRaw string, slippageBPS int) (jupiterQuoteSummary, error) {
	key := strings.Join([]string{
		strings.TrimSpace(inputMint),
		strings.TrimSpace(outputMint),
		strings.TrimSpace(amountRaw),
		strconv.Itoa(slippageBPS),
	}, "|")
	c.mu.Lock()
	if cached, ok := c.cache[key]; ok {
		c.mu.Unlock()
		return cached, nil
	}
	now := time.Now()
	if now.Before(c.cooldownUntil) {
		remaining := c.cooldownUntil.Sub(now).Round(time.Millisecond)
		c.mu.Unlock()
		return jupiterQuoteSummary{}, fmt.Errorf("jupiter funding quote cooldown active for %s", remaining)
	}
	wait := solanaFundingQuoteMinGap - now.Sub(c.lastRequest)
	c.mu.Unlock()
	if wait > 0 {
		select {
		case <-ctx.Done():
			return jupiterQuoteSummary{}, ctx.Err()
		case <-time.After(wait):
		}
	}

	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		_, quote, err := fetchJupiterQuote(ctx, inputMint, outputMint, amountRaw, slippageBPS)
		now = time.Now()
		c.mu.Lock()
		c.lastRequest = now
		if err == nil {
			c.cache[key] = quote
			c.mu.Unlock()
			return quote, nil
		}
		lastErr = err
		if strings.Contains(err.Error(), "status=429") {
			c.cooldownUntil = now.Add(solanaFundingQuoteCooldown)
			c.mu.Unlock()
			if attempt == 0 {
				select {
				case <-ctx.Done():
					return jupiterQuoteSummary{}, ctx.Err()
				case <-time.After(solanaFundingQuoteRetryGap):
				}
				continue
			}
			return jupiterQuoteSummary{}, lastErr
		}
		c.mu.Unlock()
		return jupiterQuoteSummary{}, err
	}
	return jupiterQuoteSummary{}, lastErr
}
