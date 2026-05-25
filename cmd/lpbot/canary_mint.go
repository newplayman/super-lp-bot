//go:build live

package main

import (
	"context"
	"fmt"
	"math/big"
	"net/http"
	"os"
	"strings"
	"time"

	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

const canaryMintConfirmEnv = "LPBOT_CONFIRM_CANARY_MINT"

func runCanaryMint(ctx context.Context, cfg *config.Config) (err error) {
	if os.Getenv(canaryMintConfirmEnv) != "YES" {
		return fmt.Errorf("canary mint requires %s=YES", canaryMintConfirmEnv)
	}
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()
	positionID := ""
	poolID := ""
	walletAddress := ""
	defer func() {
		if err != nil {
			_ = state.Record(ctx, canaryEvent{
				Command:    "canary_mint",
				Stage:      "failed",
				Status:     "failed",
				PositionID: positionID,
				PoolID:     poolID,
				Wallet:     walletAddress,
				ErrorMsg:   err.Error(),
			})
		}
	}()
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_mint",
		Stage:   "started",
		Status:  "running",
		Message: "manual canary mint command started",
	}); err != nil {
		return err
	}
	gate := newLiveSafetyGate("live", cfg)
	if err := gate.requireManualCanary("canary mint"); err != nil {
		return err
	}
	if len(cfg.Live.AllowedPools) != 1 {
		return fmt.Errorf("canary mint requires exactly one allowed pool, got %d", len(cfg.Live.AllowedPools))
	}

	provider, err := newCanaryMintProvider(ctx, cfg)
	if err != nil {
		return err
	}
	wallet, err := openCanaryPreflightWallet(ctx, cfg, provider)
	if err != nil {
		return err
	}
	defer wallet.Close()
	walletAddress = wallet.Address().String()

	broadcaster, err := newCanaryMintBroadcaster(ctx, cfg, provider)
	if err != nil {
		return err
	}

	amountUSD, err := selectCanaryAmountUSD(cfg)
	if err != nil {
		return err
	}
	pool, err := loadCanaryPreflightPool(ctx, provider, strings.TrimSpace(cfg.Live.AllowedPools[0]))
	if err != nil {
		return err
	}
	poolID = pool.ID
	if err := checkCanaryPreflightOpen(gate, pool, amountUSD); err != nil {
		return err
	}
	approval, err := state.RequireRecentShadowApproval(ctx, pool.ID, canaryShadowApprovalMaxAge)
	if err != nil {
		return err
	}
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_mint",
		Stage:   "strategy_quality_ok",
		Status:  "ok",
		PoolID:  pool.ID,
		Wallet:  wallet.Address().String(),
		Message: fmt.Sprintf("recent shadow approval score=%.2f age=%ds action=%s stage=%s", approval.ScoreTotal, approval.AgeSeconds, approval.FinalAction, approval.PipelineStage),
	}); err != nil {
		return err
	}

	now := time.Now()
	positionID = shadowID("canary-live-pos", pool.Key(), now.Unix())
	intent, err := buildBaseOpenIntent(ctx, provider, wallet.Address(), pool, amountUSD, positionID, now)
	if err != nil {
		return fmt.Errorf("build mint sizing: %w", err)
	}
	requiredUSDC := amountForToken(pool, baseUSDCAddress, intent)
	requiredWETH := amountForToken(pool, baseWETHAddress, intent)
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_mint",
		Stage:           "intent_built",
		Status:          "ok",
		PositionID:      positionID,
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: requiredUSDC.String(),
		RequiredWETHRaw: requiredWETH.String(),
		Message:         "mint token sizing completed",
	}); err != nil {
		return err
	}
	if err := checkCanaryMintPrerequisites(ctx, cfg, provider, wallet, requiredUSDC, requiredWETH); err != nil {
		return err
	}
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_mint",
		Stage:           "prerequisites_ok",
		Status:          "ok",
		PositionID:      positionID,
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: requiredUSDC.String(),
		RequiredWETHRaw: requiredWETH.String(),
		Message:         "balances and allowances satisfy mint requirements",
	}); err != nil {
		return err
	}

	orderManager := &orderManagerAdapter{
		provider:          provider,
		walletAddress:     wallet.Address(),
		npmBaseAddress:    strings.TrimSpace(cfg.Execution.NPMBaseAddress),
		txDeadlineSeconds: positiveOrDefault(cfg.Execution.TxDeadlineSeconds, 300),
		mintSlippageBps:   cfg.Execution.MintSlippageBps,
	}
	prepared, err := orderManager.buildPreparedMintTx(ctx, pool, amountUSD, positionID, now)
	if err != nil {
		return fmt.Errorf("build mint tx: %w", err)
	}
	preflightCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
	gas, err := estimatePreflightGas(preflightCtx, provider, prepared.UnsignedTx)
	cancel()
	if err != nil {
		return fmt.Errorf("estimate mint gas: %w", err)
	}
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_mint",
		Stage:           "preflight_ok",
		Status:          "ok",
		PositionID:      positionID,
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: requiredUSDC.String(),
		RequiredWETHRaw: requiredWETH.String(),
		GasEstimate:     gas,
		Message:         "mint gas estimate completed",
	}); err != nil {
		return err
	}
	economics, err := state.EvaluateCanaryOpenEconomics(ctx, pool, amountUSD, gas, provider)
	if err != nil {
		return err
	}
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_mint",
		Stage:           "profitability_ok",
		Status:          "ok",
		PositionID:      positionID,
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: requiredUSDC.String(),
		RequiredWETHRaw: requiredWETH.String(),
		GasEstimate:     gas,
		Message: fmt.Sprintf(
			"size_usd=%s projected_gross_usd=%s source=%s recent_avg_gross_usd=%s recent_avg_gross_per_usd=%s recent_rounds=%d recent_win_rate=%s shadow_avg_gross_usd=%s shadow_avg_gross_per_usd=%s shadow_rounds=%d shadow_win_rate=%s effective_gross_usd=%s effective_gross_per_usd=%s gas_usd=%s coverage=%s eth_price_usd=%s gas_price_gwei=%s",
			economics.RequestedAmountUSD.StringFixed(2),
			economics.ProjectedGrossUSD.StringFixed(6),
			economics.ProjectionSource,
			economics.RecentAvgGrossUSD.StringFixed(6),
			economics.RecentAvgGrossPerUSD.StringFixed(6),
			economics.RecentRounds,
			economics.RecentWinRate.StringFixed(4),
			economics.ShadowAvgGrossUSD.StringFixed(6),
			economics.ShadowAvgGrossPerUSD.StringFixed(6),
			economics.ShadowRounds,
			economics.ShadowWinRate.StringFixed(4),
			economics.EffectiveGrossUSD.StringFixed(6),
			economics.EffectiveGrossPerUSD.StringFixed(6),
			economics.EstimatedGasUSD.StringFixed(6),
			economics.CoverageRatio.StringFixed(4),
			economics.ETHPriceUSD.StringFixed(4),
			economics.GasPriceGwei.StringFixed(4),
		),
	}); err != nil {
		return err
	}
	signCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
	signed, err := wallet.Sign(signCtx, prepared.UnsignedTx)
	cancel()
	if err != nil {
		return fmt.Errorf("sign mint: %w", err)
	}
	signed.ID = prepared.ID
	signed.Status = domain.TxBuilt
	if err := state.RecordSignedTx(ctx, signed, domain.TxBuilt); err != nil {
		return fmt.Errorf("persist built mint tx: %w", err)
	}
	if err := state.Record(ctx, canaryEvent{
		Command:     "canary_mint",
		Stage:       "signed",
		Status:      "built",
		PositionID:  positionID,
		PoolID:      pool.ID,
		Wallet:      wallet.Address().String(),
		TxHash:      signed.Hash,
		AmountUSD:   amountUSD.String(),
		GasEstimate: gas,
		Message:     "mint transaction signed and persisted",
	}); err != nil {
		return err
	}
	if err := broadcaster.Send(ctx, signed); err != nil {
		return fmt.Errorf("broadcast mint: %w", err)
	}
	if err := state.RecordSignedTx(ctx, signed, domain.TxBroadcast); err != nil {
		return fmt.Errorf("persist broadcast mint tx: %w", err)
	}
	if err := state.SaveOpeningPosition(ctx, positionID, pool, amountUSD, now.Unix()); err != nil {
		return fmt.Errorf("persist opening position: %w", err)
	}
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_mint",
		Stage:           "broadcast",
		Status:          "broadcast",
		PositionID:      positionID,
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		TxHash:          signed.Hash,
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: requiredUSDC.String(),
		RequiredWETHRaw: requiredWETH.String(),
		GasEstimate:     gas,
		Message:         "mint transaction broadcast; position stored as opening until NFT token_id is reconciled",
	}); err != nil {
		return err
	}
	fmt.Printf("tx_broadcast action=mint_lp hash=%s position=%s gas_estimate=%d required_usdc=%s required_weth=%s\n",
		signed.Hash, positionID, gas, requiredUSDC.String(), requiredWETH.String())
	return nil
}

func newCanaryMintBroadcaster(ctx context.Context, cfg *config.Config, provider *rpc.RoundRobinProvider) (ports.Broadcaster, error) {
	baseRPCURL := strings.TrimSpace(cfg.Chains.Base.RPCPrimary)
	if baseRPCURL == "" && provider != nil {
		baseRPCURL = provider.Endpoint()
	}
	return livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:    baseRPCURL,
		Confirmations: cfg.Chains.Base.Confirmations,
	})
}

func newCanaryMintProvider(ctx context.Context, cfg *config.Config) (*rpc.RoundRobinProvider, error) {
	endpoints := []string{cfg.Chains.Base.RPCPrimary}
	endpoints = append(endpoints, cfg.Chains.Base.RPCFallback...)
	endpoints = append(endpoints, "https://base.drpc.org")
	return rpc.NewRoundRobinProvider(rpc.Config{
		ChainID:             domain.ChainBase,
		Endpoints:           endpoints,
		HTTPClient:          &http.Client{Timeout: 5 * time.Second},
		HealthCheckInterval: time.Minute,
		HealthCheckTimeout:  2 * time.Second,
	})
}

func checkCanaryMintPrerequisites(
	ctx context.Context,
	cfg *config.Config,
	provider *rpc.RoundRobinProvider,
	wallet ports.Wallet,
	requiredUSDC *big.Int,
	requiredWETH *big.Int,
) error {
	spender := parseAddressOrZero(strings.TrimSpace(cfg.Execution.NPMBaseAddress))
	if spender.IsZero() {
		return fmt.Errorf("npm base address is invalid")
	}
	usdcBalance, err := dashboardERC20Balance(ctx, provider, baseUSDCAddress, wallet.Address())
	if err != nil {
		return fmt.Errorf("read USDC balance: %w", err)
	}
	wethBalance, err := dashboardERC20Balance(ctx, provider, baseWETHAddress, wallet.Address())
	if err != nil {
		return fmt.Errorf("read WETH balance: %w", err)
	}
	usdcAllowance, err := dashboardERC20Allowance(ctx, provider, baseUSDCAddress, wallet.Address(), spender)
	if err != nil {
		return fmt.Errorf("read USDC allowance: %w", err)
	}
	wethAllowance, err := dashboardERC20Allowance(ctx, provider, baseWETHAddress, wallet.Address(), spender)
	if err != nil {
		return fmt.Errorf("read WETH allowance: %w", err)
	}
	if usdcBalance.Cmp(requiredUSDC) < 0 {
		return fmt.Errorf("insufficient USDC for mint: need %s raw, have %s raw", requiredUSDC.String(), usdcBalance.String())
	}
	if wethBalance.Cmp(requiredWETH) < 0 {
		return fmt.Errorf("insufficient WETH for mint: need %s raw, have %s raw", requiredWETH.String(), wethBalance.String())
	}
	if usdcAllowance.Cmp(requiredUSDC) < 0 {
		return fmt.Errorf("insufficient USDC allowance for mint: need %s raw, have %s raw", requiredUSDC.String(), usdcAllowance.String())
	}
	if wethAllowance.Cmp(requiredWETH) < 0 {
		return fmt.Errorf("insufficient WETH allowance for mint: need %s raw, have %s raw", requiredWETH.String(), wethAllowance.String())
	}
	fmt.Printf("canary mint prerequisites ok required_usdc=%s required_weth=%s balances_usdc=%s balances_weth=%s allowances_usdc=%s allowances_weth=%s\n",
		requiredUSDC.String(), requiredWETH.String(), usdcBalance.String(), wethBalance.String(), usdcAllowance.String(), wethAllowance.String())
	return nil
}
