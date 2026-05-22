//go:build live

package main

import (
	"context"
	"fmt"
	"math/big"
	"net/http"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	npmabi "github.com/lpbot/lpbot/internal/adapters/chain/base/abi"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const canaryExitPreflightSlippageBps = 100

type canaryExitPreflightReport struct {
	TokenID              string
	Owner                string
	Wallet               string
	PoolID               string
	TickLower            int64
	TickUpper            int64
	Liquidity            string
	Principal0Raw        *big.Int
	Principal1Raw        *big.Int
	Fee0Raw              *big.Int
	Fee1Raw              *big.Int
	Token0               domain.Address
	Token1               domain.Address
	Decimals0            uint8
	Decimals1            uint8
	PrincipalUSD         domain.Decimal
	FeeUSD               domain.Decimal
	TotalUSD             domain.Decimal
	DecreaseGas          uint64
	CollectCurrentFeeGas uint64
}

func runCanaryExitPreflight(ctx context.Context, cfg *config.Config, tokenID string) error {
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	tokenID = strings.TrimSpace(tokenID)
	if tokenID == "" {
		return fmt.Errorf("--token-id is required")
	}
	gate := newLiveSafetyGate("live", cfg)
	if gate.killSwitch {
		return fmt.Errorf("canary exit preflight blocked: live.kill_switch=true")
	}
	if !gate.canary {
		return fmt.Errorf("canary exit preflight requires live.canary=true")
	}
	if len(cfg.Live.AllowedPools) != 1 {
		return fmt.Errorf("canary exit preflight requires exactly one allowed pool, got %d", len(cfg.Live.AllowedPools))
	}

	provider, err := newCanaryExitPreflightProvider(ctx, cfg)
	if err != nil {
		return err
	}
	wallet, err := openCanaryPreflightWallet(ctx, cfg, provider)
	if err != nil {
		return err
	}
	defer wallet.Close()

	pool, err := loadCanaryPreflightPool(ctx, provider, strings.TrimSpace(cfg.Live.AllowedPools[0]))
	if err != nil {
		return err
	}
	if err := checkCanaryExitGate(gate, pool); err != nil {
		return err
	}
	report, err := buildCanaryExitPreflightReport(ctx, cfg, provider, wallet.Address(), pool, tokenID)
	if err != nil {
		return err
	}
	printCanaryExitPreflightReport(report)
	return nil
}

func newCanaryExitPreflightProvider(ctx context.Context, cfg *config.Config) (*rpc.RoundRobinProvider, error) {
	endpoints := []string{cfg.Chains.Base.RPCPrimary}
	endpoints = append(endpoints, cfg.Chains.Base.RPCFallback...)
	return rpc.NewRoundRobinProvider(rpc.Config{
		ChainID:             domain.ChainBase,
		Endpoints:           endpoints,
		HTTPClient:          &http.Client{Timeout: 8 * time.Second},
		HealthCheckInterval: time.Minute,
		HealthCheckTimeout:  3 * time.Second,
	})
}

func checkCanaryExitGate(gate *liveSafetyGate, pool domain.Pool) error {
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
	return nil
}

func buildCanaryExitPreflightReport(
	ctx context.Context,
	cfg *config.Config,
	provider *rpc.RoundRobinProvider,
	wallet domain.Address,
	pool domain.Pool,
	tokenID string,
) (canaryExitPreflightReport, error) {
	app := &App{
		config: cfg,
		rpc: map[string]*rpc.RoundRobinProvider{
			string(domain.ChainBase): provider,
		},
	}
	position := activeShadowPosition{
		ID:        "canary-exit-preflight-" + tokenID,
		PoolID:    pool.ID,
		TokenID:   tokenID,
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.NewDecimalFromFloat(cfg.Live.MaxOrderUSD),
		TickLower: int64(pool.Tick) - 1,
		TickUpper: int64(pool.Tick) + 1,
	}
	state, err := app.loadNPMPositionState(ctx, position)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	if !strings.EqualFold(state.Token0.String(), pool.Token0.String()) || !strings.EqualFold(state.Token1.String(), pool.Token1.String()) || state.Fee != uint64(pool.FeeBPS)*100 {
		return canaryExitPreflightReport{}, fmt.Errorf("token id %s does not match allowed pool %s", tokenID, pool.ID)
	}

	owner, err := readNPMOwnerOf(ctx, provider, cfg.Execution.NPMBaseAddress, tokenID)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	if !strings.EqualFold(owner.String(), wallet.String()) {
		return canaryExitPreflightReport{}, fmt.Errorf("token id %s owner %s does not match wallet %s", tokenID, owner.String(), wallet.String())
	}

	slot0, err := readV3PoolSlot0ForMark(ctx, provider, domain.MustParseAddress(pool.ID))
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	raw0Float, raw1Float, err := v3LiquidityAmountsRaw(state.Liquidity, slot0.SqrtPriceX96, state.TickLower, state.TickUpper)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	raw0 := big.NewInt(0).SetUint64(uint64(raw0Float))
	raw1 := big.NewInt(0).SetUint64(uint64(raw1Float))
	fees0, fees1, err := estimateNPMUncollectedFeesRaw(ctx, provider, pool, state)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	decimals0, err := tokenDecimals(ctx, provider, state.Token0)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	decimals1, err := tokenDecimals(ctx, provider, state.Token1)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	price0, price1, err := inferBaseTokenPricesUSD(domain.Pool{
		ID:       pool.ID,
		Chain:    domain.ChainBase,
		Protocol: "uniswap_v3",
		Token0:   state.Token0,
		Token1:   state.Token1,
		FeeBPS:   pool.FeeBPS,
		Tick:     slot0.Tick,
	}, decimals0, decimals1)
	if err != nil {
		return canaryExitPreflightReport{}, err
	}
	principalUSD := decimalFromRawAmount(raw0, decimals0).Mul(price0).Add(decimalFromRawAmount(raw1, decimals1).Mul(price1))
	feeUSD := decimalFromRawAmount(fees0, decimals0).Mul(price0).Add(decimalFromRawAmount(fees1, decimals1).Mul(price1))

	decreaseGas, err := estimateCanaryDecreaseGas(ctx, provider, cfg, wallet, tokenID, state.Liquidity, raw0, raw1)
	if err != nil {
		return canaryExitPreflightReport{}, fmt.Errorf("estimate decreaseLiquidity gas: %w", err)
	}
	collectGas, err := estimateCanaryCollectGas(ctx, provider, cfg, wallet, tokenID)
	if err != nil {
		return canaryExitPreflightReport{}, fmt.Errorf("estimate collect gas: %w", err)
	}

	return canaryExitPreflightReport{
		TokenID:              tokenID,
		Owner:                owner.String(),
		Wallet:               wallet.String(),
		PoolID:               pool.ID,
		TickLower:            state.TickLower,
		TickUpper:            state.TickUpper,
		Liquidity:            state.Liquidity.String(),
		Principal0Raw:        raw0,
		Principal1Raw:        raw1,
		Fee0Raw:              fees0,
		Fee1Raw:              fees1,
		Token0:               state.Token0,
		Token1:               state.Token1,
		Decimals0:            decimals0,
		Decimals1:            decimals1,
		PrincipalUSD:         principalUSD,
		FeeUSD:               feeUSD,
		TotalUSD:             principalUSD.Add(feeUSD),
		DecreaseGas:          decreaseGas,
		CollectCurrentFeeGas: collectGas,
	}, nil
}

func estimateNPMUncollectedFeesRaw(ctx context.Context, provider *rpc.RoundRobinProvider, pool domain.Pool, state npmPositionState) (*big.Int, *big.Int, error) {
	poolAddress := domain.MustParseAddress(pool.ID)
	currentTick, err := readV3PoolTickForMark(ctx, provider, poolAddress)
	if err != nil {
		return nil, nil, err
	}
	global0, err := callBigMethod(ctx, provider, poolAddress, "feeGrowthGlobal0X128()")
	if err != nil {
		return nil, nil, err
	}
	global1, err := callBigMethod(ctx, provider, poolAddress, "feeGrowthGlobal1X128()")
	if err != nil {
		return nil, nil, err
	}
	lowerTick, err := readV3TickFeeGrowth(ctx, provider, poolAddress, state.TickLower)
	if err != nil {
		return nil, nil, err
	}
	upperTick, err := readV3TickFeeGrowth(ctx, provider, poolAddress, state.TickUpper)
	if err != nil {
		return nil, nil, err
	}
	inside0 := feeGrowthInsideX128(global0, lowerTick.FeeGrowthOutside0X128, upperTick.FeeGrowthOutside0X128, currentTick, state.TickLower, state.TickUpper)
	inside1 := feeGrowthInsideX128(global1, lowerTick.FeeGrowthOutside1X128, upperTick.FeeGrowthOutside1X128, currentTick, state.TickLower, state.TickUpper)
	raw0 := liquidityFeeAmount(state.Liquidity, subModU256(inside0, state.FeeGrowthInside0LastX128))
	raw1 := liquidityFeeAmount(state.Liquidity, subModU256(inside1, state.FeeGrowthInside1LastX128))
	if state.TokensOwed0 != nil {
		raw0.Add(raw0, state.TokensOwed0)
	}
	if state.TokensOwed1 != nil {
		raw1.Add(raw1, state.TokensOwed1)
	}
	return raw0, raw1, nil
}

func estimateCanaryDecreaseGas(ctx context.Context, provider *rpc.RoundRobinProvider, cfg *config.Config, wallet domain.Address, tokenID string, liquidity *big.Int, amount0Raw *big.Int, amount1Raw *big.Int) (uint64, error) {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		return 0, fmt.Errorf("invalid token id %q", tokenID)
	}
	amount0Min := big.NewInt(0)
	amount1Min := big.NewInt(0)
	data, err := npmabi.NPMABI.Pack("decreaseLiquidity", token, liquidity, amount0Min, amount1Min, big.NewInt(time.Now().Add(10*time.Minute).Unix()))
	if err != nil {
		return 0, err
	}
	return estimateNPMGas(ctx, provider, cfg, wallet, data)
}

func estimateCanaryCollectGas(ctx context.Context, provider *rpc.RoundRobinProvider, cfg *config.Config, wallet domain.Address, tokenID string) (uint64, error) {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		return 0, fmt.Errorf("invalid token id %q", tokenID)
	}
	maxUint128 := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
	data, err := npmabi.NPMABI.Pack("collect", token, common.HexToAddress(wallet.String()), maxUint128, maxUint128)
	if err != nil {
		return 0, err
	}
	return estimateNPMGas(ctx, provider, cfg, wallet, data)
}

func estimateNPMGas(ctx context.Context, provider *rpc.RoundRobinProvider, cfg *config.Config, wallet domain.Address, data []byte) (uint64, error) {
	npmAddress := strings.TrimSpace(cfg.Execution.NPMBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	to := common.HexToAddress(npmAddress)
	return provider.EstimateGas(ctx, ethereum.CallMsg{
		From: common.HexToAddress(wallet.String()),
		To:   &to,
		Data: data,
	})
}

func readNPMOwnerOf(ctx context.Context, provider *rpc.RoundRobinProvider, npmAddress string, tokenID string) (domain.Address, error) {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		return domain.Address{}, fmt.Errorf("invalid token id %q", tokenID)
	}
	npmAddress = strings.TrimSpace(npmAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	data := make([]byte, 4+32)
	copy(data[:4], common.FromHex("0x6352211e"))
	copy(data[4+32-len(token.Bytes()):], token.Bytes())
	to := common.HexToAddress(npmAddress)
	raw, err := provider.CallContract(ctx, ethereum.CallMsg{
		To:   &to,
		Data: data,
	}, nil)
	if err != nil {
		return domain.Address{}, fmt.Errorf("read ownerOf(%s): %w", tokenID, err)
	}
	if len(raw) < 32 {
		return domain.Address{}, fmt.Errorf("ownerOf(%s) returned short response", tokenID)
	}
	return domain.ParseAddress(common.BytesToAddress(raw[len(raw)-20:]).Hex())
}

func calculateBpsMin(value *big.Int, slippageBps int64) *big.Int {
	if value == nil || value.Sign() == 0 {
		return big.NewInt(0)
	}
	result := new(big.Int).Mul(value, big.NewInt(10000-slippageBps))
	return result.Div(result, big.NewInt(10000))
}

func printCanaryExitPreflightReport(report canaryExitPreflightReport) {
	fmt.Printf("canary_exit_preflight token_id=%s owner=%s wallet=%s pool=%s tick_lower=%d tick_upper=%d liquidity=%s\n",
		report.TokenID, report.Owner, report.Wallet, report.PoolID, report.TickLower, report.TickUpper, report.Liquidity)
	fmt.Printf("canary_exit_amounts token0=%s amount0=%s raw0=%s fee0=%s token1=%s amount1=%s raw1=%s fee1=%s\n",
		report.Token0.String(),
		formatTokenBalance(new(big.Int).Add(report.Principal0Raw, report.Fee0Raw), int(report.Decimals0)),
		report.Principal0Raw.String(),
		report.Fee0Raw.String(),
		report.Token1.String(),
		formatTokenBalance(new(big.Int).Add(report.Principal1Raw, report.Fee1Raw), int(report.Decimals1)),
		report.Principal1Raw.String(),
		report.Fee1Raw.String())
	fmt.Printf("canary_exit_value principal_usd=%s fee_usd=%s total_usd=%s\n",
		report.PrincipalUSD.String(), report.FeeUSD.String(), report.TotalUSD.String())
	fmt.Printf("canary_exit_gas decrease_liquidity=%d collect_current_fees=%d slippage_bps=%d broadcast=false\n",
		report.DecreaseGas, report.CollectCurrentFeeGas, canaryExitPreflightSlippageBps)
}
