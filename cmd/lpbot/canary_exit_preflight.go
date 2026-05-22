//go:build live

package main

import (
	"context"
	"database/sql"
	"fmt"
	"math/big"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	_ "github.com/lib/pq"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const canaryExitPreflightSlippageBps = 100
const canaryExitConfirmEnv = "LPBOT_CONFIRM_CANARY_EXIT"

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

func runCanaryExitPreflight(ctx context.Context, cfg *config.Config, tokenID string) (err error) {
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	tokenID = strings.TrimSpace(tokenID)
	if tokenID == "" {
		return fmt.Errorf("--token-id is required")
	}
	stateWriter, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer stateWriter.Close()
	defer func() {
		if err != nil {
			_ = stateWriter.Record(ctx, canaryEvent{
				Command:  "canary_exit_preflight",
				Stage:    "failed",
				Status:   "failed",
				TokenID:  tokenID,
				ErrorMsg: err.Error(),
			})
		}
	}()
	if err := stateWriter.Record(ctx, canaryEvent{
		Command: "canary_exit_preflight",
		Stage:   "started",
		Status:  "running",
		TokenID: tokenID,
		Message: "manual canary exit preflight command started",
	}); err != nil {
		return err
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
	if err := persistCanaryExitPreflight(ctx, cfg, report, false, "preflight"); err != nil {
		return err
	}
	if err := stateWriter.Record(ctx, canaryEvent{
		Command:     "canary_exit_preflight",
		Stage:       "preflight_ok",
		Status:      "ok",
		PoolID:      report.PoolID,
		Wallet:      report.Wallet,
		TokenID:     tokenID,
		GasEstimate: report.DecreaseGas + report.CollectCurrentFeeGas,
		Message:     "exit preflight persisted",
	}); err != nil {
		return err
	}
	return nil
}

func runCanaryExit(ctx context.Context, cfg *config.Config, tokenID string) (err error) {
	if os.Getenv(canaryExitConfirmEnv) != "YES" {
		return fmt.Errorf("canary exit requires %s=YES", canaryExitConfirmEnv)
	}
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	tokenID = strings.TrimSpace(tokenID)
	stateWriter, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer stateWriter.Close()
	positionID, err := requireOpenLiveCanaryPositionToken(ctx, stateWriter.db, tokenID)
	if err != nil {
		return err
	}
	defer func() {
		if err != nil {
			_ = stateWriter.Record(ctx, canaryEvent{
				Command:  "canary_exit",
				Stage:    "failed",
				Status:   "failed",
				TokenID:  tokenID,
				ErrorMsg: err.Error(),
			})
		}
	}()
	if err := stateWriter.Record(ctx, canaryEvent{
		Command:    "canary_exit",
		Stage:      "started",
		Status:     "running",
		PositionID: positionID,
		TokenID:    tokenID,
		Message:    "manual canary exit command started",
	}); err != nil {
		return err
	}

	gate := newLiveSafetyGate("live", cfg)
	if gate.killSwitch {
		return fmt.Errorf("canary exit blocked: live.kill_switch=true")
	}
	if !gate.canary {
		return fmt.Errorf("canary exit requires live.canary=true")
	}
	if len(cfg.Live.AllowedPools) != 1 {
		return fmt.Errorf("canary exit requires exactly one allowed pool, got %d", len(cfg.Live.AllowedPools))
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

	broadcaster, err := newCanaryMintBroadcaster(ctx, cfg, provider)
	if err != nil {
		return err
	}
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
	if err := persistCanaryExitPreflight(ctx, cfg, report, false, "preflight_before_exit"); err != nil {
		return err
	}
	if err := stateWriter.Record(ctx, canaryEvent{
		Command:     "canary_exit",
		Stage:       "preflight_ok",
		Status:      "ok",
		PositionID:  positionID,
		PoolID:      report.PoolID,
		Wallet:      report.Wallet,
		TokenID:     tokenID,
		GasEstimate: report.DecreaseGas + report.CollectCurrentFeeGas,
		Message:     "exit preflight before broadcast persisted",
	}); err != nil {
		return err
	}

	app := &App{
		config: cfg,
		rpc: map[string]*rpc.RoundRobinProvider{
			string(domain.ChainBase): provider,
		},
	}
	state, err := app.loadNPMPositionState(ctx, activeShadowPosition{
		ID:        "canary-exit-" + tokenID,
		PoolID:    pool.ID,
		TokenID:   tokenID,
		Chain:     domain.ChainBase,
		Status:    domain.StatusOpen,
		AmountUSD: domain.NewDecimalFromFloat(cfg.Live.MaxOrderUSD),
	})
	if err != nil {
		return err
	}

	decreaseData := encodeNPMDecreaseLiquidityCalldata(
		mustTokenIDBig(tokenID),
		state.Liquidity,
		big.NewInt(0),
		big.NewInt(0),
		big.NewInt(time.Now().Add(10*time.Minute).Unix()),
	)
	decreaseTx := buildCanaryNPMUnsignedTx(cfg, wallet.Address(), decreaseData, "canary-exit-decrease-"+tokenID)
	decreaseSigned, err := sendCanaryExitTx(ctx, wallet, broadcaster, decreaseTx, "decrease_liquidity")
	if err != nil {
		_ = persistCanaryExitExecution(ctx, cfg, report, nil, nil, "exit_failed", err.Error())
		return err
	}
	if err := persistCanaryExitExecution(ctx, cfg, report, &decreaseSigned, nil, "decrease_confirmed", ""); err != nil {
		return err
	}
	if err := stateWriter.Record(ctx, canaryEvent{
		Command: "canary_exit",
		Stage:   "decrease_broadcast",
		Status:  "broadcast",
		PoolID:  report.PoolID,
		Wallet:  report.Wallet,
		TokenID: tokenID,
		TxHash:  decreaseSigned.Hash,
		Message: "decrease liquidity transaction broadcast and persisted",
	}); err != nil {
		return err
	}

	collectData := encodeNPMCollectCalldata(
		mustTokenIDBig(tokenID),
		common.HexToAddress(wallet.Address().String()),
		new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1)),
		new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1)),
	)
	collectTx := buildCanaryNPMUnsignedTx(cfg, wallet.Address(), collectData, "canary-exit-collect-"+tokenID)
	collectSigned, err := sendCanaryExitTx(ctx, wallet, broadcaster, collectTx, "collect")
	if err != nil {
		_ = persistCanaryExitExecution(ctx, cfg, report, &decreaseSigned, nil, "collect_failed", err.Error())
		return err
	}
	if err := persistCanaryExitExecution(ctx, cfg, report, &decreaseSigned, &collectSigned, "closed", ""); err != nil {
		return err
	}
	if err := stateWriter.Record(ctx, canaryEvent{
		Command: "canary_exit",
		Stage:   "collect_broadcast",
		Status:  "broadcast",
		PoolID:  report.PoolID,
		Wallet:  report.Wallet,
		TokenID: tokenID,
		TxHash:  collectSigned.Hash,
		Message: "collect transaction broadcast and position marked closed",
	}); err != nil {
		return err
	}

	fmt.Printf("canary_exit_complete token_id=%s decrease_gas_preflight=%d collect_gas_preflight=%d\n",
		tokenID, report.DecreaseGas, report.CollectCurrentFeeGas)
	return nil
}

func requireOpenLiveCanaryPositionToken(ctx context.Context, db *sql.DB, tokenID string) (string, error) {
	tokenID = strings.TrimSpace(tokenID)
	if tokenID == "" {
		return "", fmt.Errorf("--token-id is required")
	}
	var positionID string
	err := db.QueryRowContext(ctx, `
		SELECT id
		FROM positions
		WHERE token_id = $1
		  AND id LIKE 'shadow-canary-live-pos-%'
		  AND status IN ('opening', 'open')
		ORDER BY opened_at DESC
		LIMIT 1
	`, tokenID).Scan(&positionID)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("canary exit blocked: token_id %s is not an open reconciled live canary position", tokenID)
	}
	if err != nil {
		return "", fmt.Errorf("read live canary position for exit: %w", err)
	}
	return positionID, nil
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
	time.Sleep(1200 * time.Millisecond)
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
	data := encodeNPMDecreaseLiquidityCalldata(token, liquidity, amount0Min, amount1Min, big.NewInt(time.Now().Add(10*time.Minute).Unix()))
	return estimateNPMGas(ctx, provider, cfg, wallet, data)
}

func estimateCanaryCollectGas(ctx context.Context, provider *rpc.RoundRobinProvider, cfg *config.Config, wallet domain.Address, tokenID string) (uint64, error) {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		return 0, fmt.Errorf("invalid token id %q", tokenID)
	}
	maxUint128 := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
	data := encodeNPMCollectCalldata(token, common.HexToAddress(wallet.String()), maxUint128, maxUint128)
	return estimateNPMGas(ctx, provider, cfg, wallet, data)
}

func encodeNPMDecreaseLiquidityCalldata(tokenID *big.Int, liquidity *big.Int, amount0Min *big.Int, amount1Min *big.Int, deadline *big.Int) []byte {
	data := make([]byte, 0, 4+32*5)
	data = append(data, crypto.Keccak256([]byte("decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))"))[:4]...)
	data = append(data, leftPadWord(tokenID)...)
	data = append(data, leftPadWord(liquidity)...)
	data = append(data, leftPadWord(amount0Min)...)
	data = append(data, leftPadWord(amount1Min)...)
	data = append(data, leftPadWord(deadline)...)
	return data
}

func encodeNPMCollectCalldata(tokenID *big.Int, recipient common.Address, amount0Max *big.Int, amount1Max *big.Int) []byte {
	data := make([]byte, 0, 4+32*4)
	data = append(data, crypto.Keccak256([]byte("collect((uint256,address,uint128,uint128))"))[:4]...)
	data = append(data, leftPadWord(tokenID)...)
	data = append(data, common.LeftPadBytes(recipient.Bytes(), 32)...)
	data = append(data, leftPadWord(amount0Max)...)
	data = append(data, leftPadWord(amount1Max)...)
	return data
}

func leftPadWord(value *big.Int) []byte {
	if value == nil {
		value = big.NewInt(0)
	}
	return common.LeftPadBytes(value.Bytes(), 32)
}

func estimateNPMGas(ctx context.Context, provider *rpc.RoundRobinProvider, cfg *config.Config, wallet domain.Address, data []byte) (uint64, error) {
	npmAddress := strings.TrimSpace(cfg.Execution.NPMBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	to := common.HexToAddress(npmAddress)
	msg := ethereum.CallMsg{
		From: common.HexToAddress(wallet.String()),
		To:   &to,
		Data: data,
	}
	var lastErr error
	for attempt := 0; attempt < 4; attempt++ {
		gas, err := provider.EstimateGas(ctx, msg)
		if err == nil {
			return gas, nil
		}
		lastErr = err
		if !strings.Contains(strings.ToLower(err.Error()), "429") && !strings.Contains(strings.ToLower(err.Error()), "too many requests") {
			return 0, err
		}
		time.Sleep(time.Duration(attempt+1) * 1500 * time.Millisecond)
	}
	return 0, lastErr
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

func mustTokenIDBig(tokenID string) *big.Int {
	token, ok := new(big.Int).SetString(tokenID, 10)
	if !ok || token.Sign() <= 0 {
		panic("invalid token id")
	}
	return token
}

func buildCanaryNPMUnsignedTx(cfg *config.Config, wallet domain.Address, data []byte, id string) domain.UnsignedTx {
	npmAddress := strings.TrimSpace(cfg.Execution.NPMBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	return domain.UnsignedTx{
		ID:       id,
		Chain:    domain.ChainBase,
		From:     wallet,
		To:       domain.MustParseAddress(npmAddress),
		Value:    domain.ZeroDecimal(),
		Data:     data,
		Deadline: time.Now().Add(10 * time.Minute).Unix(),
		MinOut:   domain.ZeroDecimal(),
	}
}

func sendCanaryExitTx(ctx context.Context, wallet interface {
	Sign(context.Context, domain.UnsignedTx) (domain.SignedTx, error)
}, broadcaster interface {
	Send(context.Context, domain.SignedTx) error
}, tx domain.UnsignedTx, action string) (domain.SignedTx, error) {
	signCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
	signed, err := wallet.Sign(signCtx, tx)
	cancel()
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("sign %s: %w", action, err)
	}
	signed.ID = tx.ID
	signed.Status = domain.TxBuilt
	sendCtx, cancel := context.WithTimeout(ctx, 180*time.Second)
	err = broadcaster.Send(sendCtx, signed)
	cancel()
	if err != nil {
		signed.Status = domain.TxFailed
		return signed, fmt.Errorf("broadcast %s: %w", action, err)
	}
	signed.Status = domain.TxConfirmed
	fmt.Printf("tx_broadcast action=%s hash=%s id=%s\n", action, signed.Hash, signed.ID)
	return signed, nil
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

func persistCanaryExitPreflight(ctx context.Context, cfg *config.Config, report canaryExitPreflightReport, broadcastEnabled bool, status string) error {
	dsn := strings.TrimSpace(cfg.Store.PostgresDSN)
	if dsn == "" {
		return fmt.Errorf("store.postgres_dsn is empty; cannot persist canary exit preflight")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return fmt.Errorf("open postgres for exit preflight: %w", err)
	}
	defer db.Close()
	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping postgres for exit preflight: %w", err)
	}
	if err := ensureCanaryExitPreflightsTable(ctx, db); err != nil {
		return err
	}
	now := time.Now().Unix()
	_, err = db.ExecContext(ctx, `
		INSERT INTO canary_exit_preflights (
			token_id, owner, wallet, pool_id, tick_lower, tick_upper, liquidity,
			token0, token1, principal0_raw, principal1_raw, fee0_raw, fee1_raw,
			principal_usd, fee_usd, total_usd, decrease_gas, collect_gas,
			slippage_bps, broadcast_enabled, status, checked_at, updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7,
			$8, $9, $10, $11, $12, $13,
			$14, $15, $16, $17, $18,
			$19, $20, $21, $22, $23
		)
		ON CONFLICT (token_id) DO UPDATE SET
			owner = excluded.owner,
			wallet = excluded.wallet,
			pool_id = excluded.pool_id,
			tick_lower = excluded.tick_lower,
			tick_upper = excluded.tick_upper,
			liquidity = excluded.liquidity,
			token0 = excluded.token0,
			token1 = excluded.token1,
			principal0_raw = excluded.principal0_raw,
			principal1_raw = excluded.principal1_raw,
			fee0_raw = excluded.fee0_raw,
			fee1_raw = excluded.fee1_raw,
			principal_usd = excluded.principal_usd,
			fee_usd = excluded.fee_usd,
			total_usd = excluded.total_usd,
			decrease_gas = excluded.decrease_gas,
			collect_gas = excluded.collect_gas,
			slippage_bps = excluded.slippage_bps,
			broadcast_enabled = excluded.broadcast_enabled,
			status = excluded.status,
			checked_at = excluded.checked_at,
			updated_at = excluded.updated_at
	`,
		report.TokenID,
		report.Owner,
		report.Wallet,
		report.PoolID,
		report.TickLower,
		report.TickUpper,
		report.Liquidity,
		report.Token0.String(),
		report.Token1.String(),
		report.Principal0Raw.String(),
		report.Principal1Raw.String(),
		report.Fee0Raw.String(),
		report.Fee1Raw.String(),
		report.PrincipalUSD.String(),
		report.FeeUSD.String(),
		report.TotalUSD.String(),
		report.DecreaseGas,
		report.CollectCurrentFeeGas,
		canaryExitPreflightSlippageBps,
		broadcastEnabled,
		status,
		now,
		now,
	)
	if err != nil {
		return fmt.Errorf("upsert canary exit preflight: %w", err)
	}
	fmt.Printf("canary_exit_preflight_persisted token_id=%s status=%s broadcast_enabled=%t checked_at=%d\n",
		report.TokenID, status, broadcastEnabled, now)
	return nil
}

func persistCanaryExitExecution(ctx context.Context, cfg *config.Config, report canaryExitPreflightReport, decreaseTx *domain.SignedTx, collectTx *domain.SignedTx, status string, errorMsg string) error {
	dsn := strings.TrimSpace(cfg.Store.PostgresDSN)
	if dsn == "" {
		return fmt.Errorf("store.postgres_dsn is empty; cannot persist canary exit execution")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return fmt.Errorf("open postgres for canary exit execution: %w", err)
	}
	defer db.Close()
	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping postgres for canary exit execution: %w", err)
	}
	if err := ensureCanaryExitPreflightsTable(ctx, db); err != nil {
		return err
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin canary exit persist tx: %w", err)
	}
	defer tx.Rollback()

	nowMilli := time.Now().UnixMilli()
	if decreaseTx != nil {
		if err := upsertCanaryExitSignedTx(ctx, tx, *decreaseTx, nowMilli); err != nil {
			return err
		}
	}
	if collectTx != nil {
		if err := upsertCanaryExitSignedTx(ctx, tx, *collectTx, nowMilli); err != nil {
			return err
		}
	}

	positionStatus := "exiting"
	closedAt := int64(0)
	if status == "closed" {
		positionStatus = string(domain.StatusClosed)
		closedAt = time.Now().Unix()
	}
	if strings.Contains(status, "failed") {
		positionStatus = string(domain.StatusExitFailed)
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE positions
		SET status = $1,
		    closed_at = CASE
		        WHEN $1 = 'closed' THEN $3
		        ELSE closed_at
		    END
		WHERE token_id = $2
	`, positionStatus, report.TokenID, closedAt); err != nil {
		return fmt.Errorf("update position after canary exit: %w", err)
	}

	decreaseHash := ""
	collectHash := ""
	if decreaseTx != nil {
		decreaseHash = decreaseTx.Hash
	}
	if collectTx != nil {
		collectHash = collectTx.Hash
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE canary_exit_preflights
		SET broadcast_enabled = TRUE,
		    status = $1,
		    decrease_tx_hash = $2,
		    collect_tx_hash = $3,
		    error_msg = $4,
		    updated_at = $5
		WHERE token_id = $6
	`, status, decreaseHash, collectHash, errorMsg, time.Now().Unix(), report.TokenID); err != nil {
		return fmt.Errorf("update canary exit preflight execution state: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit canary exit persist tx: %w", err)
	}
	fmt.Printf("canary_exit_persisted token_id=%s status=%s decrease_hash=%s collect_hash=%s\n",
		report.TokenID, status, decreaseHash, collectHash)
	return nil
}

func upsertCanaryExitSignedTx(ctx context.Context, tx *sql.Tx, signed domain.SignedTx, nowMilli int64) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO transactions (
			id, chain, tx_hash, from_address, to_address, data, value,
			nonce, deadline, min_out, signature, status,
			block_number, block_hash, broadcast_at,
			gas_used, gas_price, gas_limit,
			rfb_attempts, error_msg, trace_id, created_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
		ON CONFLICT (tx_hash) DO UPDATE SET
			status = EXCLUDED.status,
			broadcast_at = COALESCE(EXCLUDED.broadcast_at, transactions.broadcast_at),
			updated_at = EXCLUDED.updated_at
	`,
		signed.ID,
		signed.Chain,
		signed.Hash,
		signed.From.String(),
		signed.To.String(),
		signed.Data,
		signed.Value.String(),
		signed.Nonce,
		signed.Deadline,
		signed.MinOut.String(),
		signed.Signature,
		signed.Status,
		nil,
		nil,
		nowMilli,
		nil,
		nil,
		nil,
		signed.RFBAttempts,
		nil,
		nil,
		nowMilli,
		nowMilli,
	)
	if err != nil {
		return fmt.Errorf("upsert canary exit tx %s: %w", signed.ID, err)
	}
	return nil
}

func ensureCanaryExitPreflightsTable(ctx context.Context, db *sql.DB) error {
	_, err := db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS canary_exit_preflights (
			token_id TEXT PRIMARY KEY,
			owner TEXT NOT NULL DEFAULT '',
			wallet TEXT NOT NULL DEFAULT '',
			pool_id TEXT NOT NULL DEFAULT '',
			tick_lower BIGINT NOT NULL DEFAULT 0,
			tick_upper BIGINT NOT NULL DEFAULT 0,
			liquidity TEXT NOT NULL DEFAULT '0',
			token0 TEXT NOT NULL DEFAULT '',
			token1 TEXT NOT NULL DEFAULT '',
			principal0_raw TEXT NOT NULL DEFAULT '0',
			principal1_raw TEXT NOT NULL DEFAULT '0',
			fee0_raw TEXT NOT NULL DEFAULT '0',
			fee1_raw TEXT NOT NULL DEFAULT '0',
			principal_usd TEXT NOT NULL DEFAULT '0',
			fee_usd TEXT NOT NULL DEFAULT '0',
			total_usd TEXT NOT NULL DEFAULT '0',
			decrease_gas BIGINT NOT NULL DEFAULT 0,
			collect_gas BIGINT NOT NULL DEFAULT 0,
			slippage_bps BIGINT NOT NULL DEFAULT 0,
			broadcast_enabled BOOLEAN NOT NULL DEFAULT FALSE,
			decrease_tx_hash TEXT NOT NULL DEFAULT '',
			collect_tx_hash TEXT NOT NULL DEFAULT '',
			error_msg TEXT NOT NULL DEFAULT '',
			status TEXT NOT NULL DEFAULT '',
			checked_at BIGINT NOT NULL DEFAULT 0,
			updated_at BIGINT NOT NULL DEFAULT 0
		);
		ALTER TABLE canary_exit_preflights ADD COLUMN IF NOT EXISTS decrease_tx_hash TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_exit_preflights ADD COLUMN IF NOT EXISTS collect_tx_hash TEXT NOT NULL DEFAULT '';
		ALTER TABLE canary_exit_preflights ADD COLUMN IF NOT EXISTS error_msg TEXT NOT NULL DEFAULT '';
		CREATE INDEX IF NOT EXISTS idx_canary_exit_preflights_checked_at
			ON canary_exit_preflights(checked_at DESC);
	`)
	if err != nil {
		return fmt.Errorf("ensure canary_exit_preflights table: %w", err)
	}
	return nil
}
