//go:build live

package main

import (
	"context"
	"fmt"
	"math"
	"math/big"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	keystorewallet "github.com/lpbot/lpbot/internal/adapters/wallet/keystore"
	"github.com/lpbot/lpbot/internal/core/execution"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

type canaryPreflightReport struct {
	WalletAddress   string
	PoolID          string
	AmountUSD       domain.Decimal
	ETHBalanceWei   *big.Int
	USDCBalance     *big.Int
	WETHBalance     *big.Int
	USDCAllowance   *big.Int
	WETHAllowance   *big.Int
	RequiredUSDC    *big.Int
	RequiredWETH    *big.Int
	WrapRequiredWei *big.Int
	WrapGas         uint64
	USDCApprovalGas uint64
	WETHApprovalGas uint64
	MintGas         uint64
	MintSkipReason  string
	PoolFee         uint32
	PoolTick        int
}

func runCanaryPreflight(ctx context.Context, cfg *config.Config) error {
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	gate := newLiveSafetyGate("live", cfg)
	if gate.killSwitch {
		return fmt.Errorf("canary preflight blocked: live.kill_switch=true")
	}
	if !gate.canary {
		return fmt.Errorf("canary preflight requires live.canary=true")
	}
	if cfg.Live.MaxOrderUSD > canaryMaxOrderUSD {
		return fmt.Errorf("canary preflight blocked: max_order_usd %.2f exceeds hard cap %.2f", cfg.Live.MaxOrderUSD, canaryMaxOrderUSD)
	}
	if len(cfg.Live.AllowedPools) != 1 {
		return fmt.Errorf("canary preflight requires exactly one allowed pool, got %d", len(cfg.Live.AllowedPools))
	}

	provider, err := newCanaryPreflightProvider(ctx, cfg)
	if err != nil {
		return err
	}
	wallet, err := openCanaryPreflightWallet(ctx, cfg, provider)
	if err != nil {
		return err
	}
	defer wallet.Close()

	amountUSD := domain.NewDecimalFromFloat(cfg.Live.MaxOrderUSD)
	if amountUSD.LessThanOrEqual(domain.ZeroDecimal()) || amountUSD.GreaterThan(domain.NewDecimalFromFloat(canaryMaxOrderUSD)) {
		return fmt.Errorf("invalid canary amount_usd: %s", amountUSD.String())
	}
	pool, err := loadCanaryPreflightPool(ctx, provider, strings.TrimSpace(cfg.Live.AllowedPools[0]))
	if err != nil {
		return err
	}
	if err := checkCanaryPreflightOpen(gate, pool, amountUSD); err != nil {
		return err
	}
	report, err := buildCanaryPreflightReport(ctx, cfg, provider, wallet, pool, amountUSD)
	if err != nil {
		return err
	}
	printCanaryPreflightReport(report)
	return nil
}

func checkCanaryPreflightOpen(gate *liveSafetyGate, pool domain.Pool, amountUSD domain.Decimal) error {
	if gate == nil {
		return fmt.Errorf("live gate not initialized")
	}
	if gate.killSwitch {
		return fmt.Errorf("live gate blocked: live.kill_switch=true")
	}
	chain := strings.ToLower(strings.TrimSpace(string(pool.Chain)))
	if _, ok := gate.allowedChains[chain]; !ok {
		return fmt.Errorf("live gate blocked: chain %s not in allowed_chains", pool.Chain)
	}
	poolID := strings.ToLower(strings.TrimSpace(pool.ID))
	if _, ok := gate.allowedPools[poolID]; !ok {
		return fmt.Errorf("live gate blocked: pool %s not in allowed_pools", pool.ID)
	}
	maxOrder := domain.NewDecimalFromFloat(gate.maxOrderUSD)
	if gate.canary && gate.maxOrderUSD > canaryMaxOrderUSD {
		maxOrder = domain.NewDecimalFromFloat(canaryMaxOrderUSD)
	}
	if amountUSD.GreaterThan(maxOrder) {
		return fmt.Errorf("live gate blocked: amount %s exceeds max_order_usd %s", amountUSD.String(), maxOrder.String())
	}
	return nil
}

func newCanaryPreflightProvider(ctx context.Context, cfg *config.Config) (*rpc.RoundRobinProvider, error) {
	endpoints := []string{cfg.Chains.Base.RPCPrimary}
	endpoints = append(endpoints, cfg.Chains.Base.RPCFallback...)
	endpoints = append(endpoints, rpc.BasePublicEndpoints...)
	return rpc.NewRoundRobinProvider(rpc.Config{
		ChainID:             domain.ChainBase,
		Endpoints:           endpoints,
		HTTPClient:          &http.Client{Timeout: 5 * time.Second},
		HealthCheckInterval: time.Minute,
		HealthCheckTimeout:  2 * time.Second,
	})
}

func openCanaryPreflightWallet(ctx context.Context, cfg *config.Config, provider *rpc.RoundRobinProvider) (ports.Wallet, error) {
	keystorePath := strings.TrimSpace(cfg.Wallet.KeystorePath)
	if keystorePath == "" {
		return nil, fmt.Errorf("wallet.keystore_path is empty")
	}
	walletAddress := parseAddressOrZero(strings.TrimSpace(cfg.Live.WalletAddress))
	if walletAddress.IsZero() {
		return nil, fmt.Errorf("live.wallet_address is empty")
	}
	walletCfg := ports.WalletConfig{
		Type:         "keystore",
		ChainID:      domain.ChainBase,
		KeystoreDir:  filepath.Dir(keystorePath),
		KeystoreFile: filepath.Base(keystorePath),
		Passphrase:   cfg.Wallet.Passphrase,
		Address:      walletAddress,
	}
	walletProvider, err := keystorewallet.New(ctx, walletCfg)
	if err != nil {
		return nil, err
	}
	walletProvider.SetRPCProvider(provider)
	walletProvider.SetChain(provider)
	walletProvider.SetGasOracle(roundRobinGasOracle{provider: provider})
	return walletProvider.Open(ctx, walletCfg)
}

func loadCanaryPreflightPool(ctx context.Context, provider *rpc.RoundRobinProvider, poolID string) (domain.Pool, error) {
	poolAddress, err := domain.ParseAddress(poolID)
	if err != nil {
		return domain.Pool{}, fmt.Errorf("invalid canary pool: %w", err)
	}
	token0, err := callAddressMethod(ctx, provider, poolAddress, "token0()")
	if err != nil {
		return domain.Pool{}, fmt.Errorf("read pool token0: %w", err)
	}
	token1, err := callAddressMethod(ctx, provider, poolAddress, "token1()")
	if err != nil {
		return domain.Pool{}, fmt.Errorf("read pool token1: %w", err)
	}
	if !isBaseWETHUSDCPair(token0, token1) {
		return domain.Pool{}, fmt.Errorf("allowed pool is not Base WETH/USDC")
	}
	fee, err := callUintMethod(ctx, provider, poolAddress, "fee()")
	if err != nil {
		return domain.Pool{}, fmt.Errorf("read pool fee: %w", err)
	}
	tick, err := readV3PoolTick(ctx, provider, poolAddress)
	if err != nil {
		return domain.Pool{}, err
	}
	return domain.Pool{
		ID:       poolID,
		Chain:    domain.ChainBase,
		Protocol: "uniswap_v3",
		Token0:   token0,
		Token1:   token1,
		FeeBPS:   uint(fee / 100),
		Tier_:    domain.TierC,
		Tick:     tick,
	}, nil
}

func readV3PoolTick(ctx context.Context, provider *rpc.RoundRobinProvider, pool domain.Address) (int, error) {
	raw, err := callRawMethod(ctx, provider, pool, "slot0()")
	if err != nil {
		return 0, fmt.Errorf("read pool slot0: %w", err)
	}
	if len(raw) < 64 {
		return 0, fmt.Errorf("slot0 returned short response")
	}
	word := raw[32:64]
	tick := int32(word[29])<<16 | int32(word[30])<<8 | int32(word[31])
	if tick&0x800000 != 0 {
		tick -= 1 << 24
	}
	if tick < math.MinInt32 || tick > math.MaxInt32 {
		return 0, fmt.Errorf("slot0 tick out of range: %d", tick)
	}
	return int(tick), nil
}

func buildCanaryPreflightReport(
	ctx context.Context,
	cfg *config.Config,
	provider *rpc.RoundRobinProvider,
	wallet ports.Wallet,
	pool domain.Pool,
	amountUSD domain.Decimal,
) (canaryPreflightReport, error) {
	spender := parseAddressOrZero(strings.TrimSpace(cfg.Execution.NPMBaseAddress))
	if spender.IsZero() {
		return canaryPreflightReport{}, fmt.Errorf("npm base address is invalid")
	}
	intent, err := buildBaseOpenIntent(ctx, provider, wallet.Address(), pool, amountUSD, shadowID("preflight", pool.Key(), time.Now().Unix()), time.Now())
	if err != nil {
		return canaryPreflightReport{}, err
	}

	ethBalance, err := provider.BalanceAt(ctx, wallet.Address(), nil)
	if err != nil {
		return canaryPreflightReport{}, fmt.Errorf("read ETH balance: %w", err)
	}
	usdcBalance, err := dashboardERC20Balance(ctx, provider, baseUSDCAddress, wallet.Address())
	if err != nil {
		return canaryPreflightReport{}, fmt.Errorf("read USDC balance: %w", err)
	}
	wethBalance, err := dashboardERC20Balance(ctx, provider, baseWETHAddress, wallet.Address())
	if err != nil {
		return canaryPreflightReport{}, fmt.Errorf("read WETH balance: %w", err)
	}
	usdcAllowance, err := dashboardERC20Allowance(ctx, provider, baseUSDCAddress, wallet.Address(), spender)
	if err != nil {
		return canaryPreflightReport{}, fmt.Errorf("read USDC allowance: %w", err)
	}
	wethAllowance, err := dashboardERC20Allowance(ctx, provider, baseWETHAddress, wallet.Address(), spender)
	if err != nil {
		return canaryPreflightReport{}, fmt.Errorf("read WETH allowance: %w", err)
	}

	report := canaryPreflightReport{
		WalletAddress:   wallet.Address().String(),
		PoolID:          pool.ID,
		AmountUSD:       amountUSD,
		ETHBalanceWei:   ethBalance,
		USDCBalance:     usdcBalance,
		WETHBalance:     wethBalance,
		USDCAllowance:   usdcAllowance,
		WETHAllowance:   wethAllowance,
		RequiredUSDC:    amountForToken(pool, baseUSDCAddress, intent),
		RequiredWETH:    amountForToken(pool, baseWETHAddress, intent),
		WrapRequiredWei: big.NewInt(0),
		PoolFee:         intent.Fee,
		PoolTick:        pool.Tick,
	}
	if report.WETHBalance.Cmp(report.RequiredWETH) < 0 {
		report.WrapRequiredWei = new(big.Int).Sub(report.RequiredWETH, report.WETHBalance)
	}
	if report.USDCBalance.Cmp(report.RequiredUSDC) < 0 {
		return report, fmt.Errorf("insufficient USDC: need %s raw, have %s raw", report.RequiredUSDC.String(), report.USDCBalance.String())
	}

	if report.WrapRequiredWei.Sign() > 0 {
		wrapTx := domain.UnsignedTx{
			Chain:  domain.ChainBase,
			From:   wallet.Address(),
			To:     domain.MustParseAddress(baseWETHAddress),
			Data:   common.FromHex("0xd0e30db0"),
			Value:  domain.MustDecimal(report.WrapRequiredWei.String()),
			MinOut: domain.NewDecimalFromInt(1),
		}
		report.WrapGas, err = estimatePreflightGas(ctx, provider, wrapTx)
		if err != nil {
			return report, fmt.Errorf("estimate WETH wrap gas: %w", err)
		}
	}
	if report.USDCAllowance.Cmp(report.RequiredUSDC) < 0 {
		approveTx, err := wallet.ApproveExact(ctx, domain.MustParseAddress(baseUSDCAddress), spender, report.RequiredUSDC)
		if err != nil {
			return report, fmt.Errorf("build USDC approval: %w", err)
		}
		report.USDCApprovalGas, err = estimatePreflightGas(ctx, provider, approveTx)
		if err != nil {
			return report, fmt.Errorf("estimate USDC approval gas: %w", err)
		}
	}
	if report.WETHAllowance.Cmp(report.RequiredWETH) < 0 {
		approveTx, err := wallet.ApproveExact(ctx, domain.MustParseAddress(baseWETHAddress), spender, report.RequiredWETH)
		if err != nil {
			return report, fmt.Errorf("build WETH approval: %w", err)
		}
		report.WETHApprovalGas, err = estimatePreflightGas(ctx, provider, approveTx)
		if err != nil {
			return report, fmt.Errorf("estimate WETH approval gas: %w", err)
		}
	}

	if reason := mintPreflightSkipReason(report); reason != "" {
		report.MintSkipReason = reason
	} else {
		orderManager := &orderManagerAdapter{
			provider:       provider,
			walletAddress:  wallet.Address(),
			npmBaseAddress: strings.TrimSpace(cfg.Execution.NPMBaseAddress),
		}
		mintTx, err := orderManager.buildPreparedMintTx(ctx, pool, amountUSD, shadowID("preflight-pos", pool.Key(), time.Now().Unix()), time.Now())
		if err != nil {
			return report, err
		}
		report.MintGas, err = estimatePreflightGas(ctx, provider, mintTx.UnsignedTx)
		if err != nil {
			return report, fmt.Errorf("estimate mint gas: %w", err)
		}
	}
	return report, nil
}

func mintPreflightSkipReason(report canaryPreflightReport) string {
	var reasons []string
	if report.WrapRequiredWei.Sign() > 0 {
		reasons = append(reasons, "weth_wrap_required")
	}
	if report.USDCAllowance.Cmp(report.RequiredUSDC) < 0 {
		reasons = append(reasons, "usdc_approval_required")
	}
	if report.WETHAllowance.Cmp(report.RequiredWETH) < 0 {
		reasons = append(reasons, "weth_approval_required")
	}
	if len(reasons) == 0 {
		return ""
	}
	return strings.Join(reasons, ",")
}

func amountForToken(pool domain.Pool, token string, intent execution.OpenIntent) *big.Int {
	switch {
	case strings.EqualFold(pool.Token0.String(), token):
		return intent.Amount0.BigInt()
	case strings.EqualFold(pool.Token1.String(), token):
		return intent.Amount1.BigInt()
	default:
		return big.NewInt(0)
	}
	return big.NewInt(0)
}

func estimatePreflightGas(ctx context.Context, provider *rpc.RoundRobinProvider, tx domain.UnsignedTx) (uint64, error) {
	to := common.HexToAddress(tx.To.String())
	return provider.EstimateGas(ctx, ethereum.CallMsg{
		From:  common.HexToAddress(tx.From.String()),
		To:    &to,
		Value: tx.Value.BigInt(),
		Data:  tx.Data,
	})
}

func printCanaryPreflightReport(report canaryPreflightReport) {
	fmt.Println("canary preflight ok")
	fmt.Printf("wallet=%s\n", maskAddress(report.WalletAddress))
	fmt.Printf("pool=%s fee=%d tick=%d\n", report.PoolID, report.PoolFee, report.PoolTick)
	fmt.Printf("amount_usd=%s\n", report.AmountUSD.String())
	fmt.Printf("balances_raw eth=%s usdc=%s weth=%s\n", report.ETHBalanceWei.String(), report.USDCBalance.String(), report.WETHBalance.String())
	fmt.Printf("allowances_raw usdc=%s weth=%s\n", report.USDCAllowance.String(), report.WETHAllowance.String())
	fmt.Printf("required_raw usdc=%s weth=%s wrap_weth=%s\n", report.RequiredUSDC.String(), report.RequiredWETH.String(), report.WrapRequiredWei.String())
	fmt.Printf("gas_estimates wrap=%d approve_usdc=%d approve_weth=%d mint=%d\n", report.WrapGas, report.USDCApprovalGas, report.WETHApprovalGas, report.MintGas)
	if report.MintSkipReason != "" {
		fmt.Printf("mint_preflight_skipped=%s\n", report.MintSkipReason)
	}
}
