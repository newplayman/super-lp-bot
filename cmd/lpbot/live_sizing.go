package main

import (
	"context"
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/core/execution"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

var knownBaseStableTokens = map[string]struct{}{
	strings.ToLower("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"): {},
	strings.ToLower("0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"): {},
	strings.ToLower("0x60a3E35Cc302bFA44Cb288Bc5a4F316Fdb1adb42"): {},
}

func nativeRPCLiveSizingSupported(cfg *config.Config) bool {
	if cfg == nil {
		return false
	}
	if normalizeExecutionBackend(cfg.Execution.Backend) != "native-rpc" {
		return false
	}
	return strings.TrimSpace(cfg.Chains.Base.RPCPrimary) != "" || rpc.ResolveQuickNodeAPIKey() != ""
}

func liveExecutionPathAvailable(cfg *config.Config) bool {
	if cfg == nil {
		return false
	}
	if !nativeRPCLiveSizingSupported(cfg) {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(cfg.Wallet.Backend), "keystore")
}

func (o *orderManagerAdapter) buildPreparedMintTx(
	ctx context.Context,
	pool domain.Pool,
	amountUSD domain.Decimal,
	positionID string,
	now time.Time,
) (domain.SignedTx, error) {
	if o == nil {
		return domain.SignedTx{}, fmt.Errorf("order manager not configured")
	}
	if pool.Chain != domain.ChainBase {
		return domain.SignedTx{}, fmt.Errorf("live sizing only supports base pools")
	}
	if o.provider == nil {
		return domain.SignedTx{}, fmt.Errorf("base rpc provider not configured")
	}
	if o.walletAddress.IsZero() {
		return domain.SignedTx{}, fmt.Errorf("wallet address not configured")
	}
	if strings.TrimSpace(o.npmBaseAddress) == "" {
		return domain.SignedTx{}, fmt.Errorf("npm base address not configured")
	}

	intent, err := buildBaseOpenIntent(ctx, o.provider, o.walletAddress, pool, amountUSD, positionID, now)
	if err != nil {
		return domain.SignedTx{}, err
	}

	builder := execution.NewTxBuilder(nil, nil, execution.NPMConfig{Base: o.npmBaseAddress})
	calldata, to, err := builder.BuildMintCalldata(intent)
	if err != nil {
		return domain.SignedTx{}, fmt.Errorf("build mint calldata: %w", err)
	}

	txHash := shadowID("tx", positionID, now.Unix())
	return domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:       txHash,
			Chain:    pool.Chain,
			From:     intent.Recipient,
			To:       domain.MustParseAddress(to.Hex()),
			Data:     calldata,
			Value:    domain.ZeroDecimal(),
			Deadline: intent.Deadline,
			MinOut:   domain.ZeroDecimal(),
		},
		Hash:   txHash,
		Status: domain.TxBuilt,
	}, nil
}

func (o *orderManagerAdapter) preflightPreparedTx(ctx context.Context, tx domain.UnsignedTx) error {
	if o == nil || o.provider == nil {
		return fmt.Errorf("base rpc provider not configured")
	}
	to := common.HexToAddress(tx.To.String())
	_, err := o.provider.CallContract(ctx, ethereum.CallMsg{
		From:  common.HexToAddress(tx.From.String()),
		To:    &to,
		Value: tx.Value.BigInt(),
		Data:  tx.Data,
	}, nil)
	return err
}

func buildBaseOpenIntent(
	ctx context.Context,
	provider *rpc.RoundRobinProvider,
	recipient domain.Address,
	pool domain.Pool,
	amountUSD domain.Decimal,
	positionID string,
	now time.Time,
) (execution.OpenIntent, error) {
	decimals0, err := tokenDecimals(ctx, provider, pool.Token0)
	if err != nil {
		return execution.OpenIntent{}, fmt.Errorf("token0 decimals: %w", err)
	}
	decimals1, err := tokenDecimals(ctx, provider, pool.Token1)
	if err != nil {
		return execution.OpenIntent{}, fmt.Errorf("token1 decimals: %w", err)
	}

	price0USD, price1USD, err := inferBaseTokenPricesUSD(pool, decimals0, decimals1)
	if err != nil {
		return execution.OpenIntent{}, err
	}

	halfUSD := amountUSD.Div(domain.NewDecimalFromInt(2))
	amount0Display := halfUSD.Div(price0USD)
	amount1Display := halfUSD.Div(price1USD)
	amount0Raw := amount0Display.Mul(scaleForDecimals(decimals0)).Truncate(0)
	amount1Raw := amount1Display.Mul(scaleForDecimals(decimals1)).Truncate(0)
	if amount0Raw.LessThanOrEqual(domain.ZeroDecimal()) && amount1Raw.LessThanOrEqual(domain.ZeroDecimal()) {
		return execution.OpenIntent{}, fmt.Errorf("sized amounts are zero for pool %s", pool.ID)
	}
	feeRaw, err := baseV3FeeRaw(ctx, provider, pool)
	if err != nil {
		return execution.OpenIntent{}, err
	}

	tickLower, tickUpper := defaultOpenRange(pool.Tick, tickSpacingForFee(feeRaw))
	return execution.OpenIntent{
		PositionID: positionID,
		PoolID:     pool.ID,
		Chain:      pool.Chain,
		Tier:       pool.Tier_,
		AmountUSD:  amountUSD,
		TickLower:  tickLower,
		TickUpper:  tickUpper,
		TraceID:    shadowID("trace", pool.Key(), now.Unix()),
		Token0:     pool.Token0,
		Token1:     pool.Token1,
		Recipient:  recipient,
		Amount0:    amount0Raw,
		Amount1:    amount1Raw,
		// For V3 mint, actual token usage depends on current price and tick range.
		// amountDesired caps max spend; keep amountMin loose for tiny canary mints.
		SlippageBps: 9999,
		Deadline:    now.Add(5 * time.Minute).Unix(),
		Fee:         feeRaw,
	}, nil
}

func baseV3FeeRaw(ctx context.Context, provider *rpc.RoundRobinProvider, pool domain.Pool) (uint32, error) {
	if pool.FeeBPS > 0 {
		return uint32(pool.FeeBPS * 100), nil
	}
	poolAddress, err := domain.ParseAddress(pool.ID)
	if err != nil {
		return 0, fmt.Errorf("pool fee is missing and pool address is invalid: %w", err)
	}
	fee, err := callUintMethod(ctx, provider, poolAddress, "fee()")
	if err != nil {
		return 0, fmt.Errorf("read v3 pool fee: %w", err)
	}
	if fee == 0 || fee > math.MaxUint32 {
		return 0, fmt.Errorf("invalid v3 pool fee: %d", fee)
	}
	return uint32(fee), nil
}

func tokenDecimals(ctx context.Context, provider *rpc.RoundRobinProvider, token domain.Address) (uint8, error) {
	raw, err := callUintMethod(ctx, provider, token, "decimals()")
	if err != nil {
		return 0, err
	}
	if raw > math.MaxUint8 {
		return 0, fmt.Errorf("decimals overflow: %d", raw)
	}
	return uint8(raw), nil
}

func inferBaseTokenPricesUSD(pool domain.Pool, decimals0, decimals1 uint8) (domain.Decimal, domain.Decimal, error) {
	priceRatio := priceRatioFromTick(pool.Tick, decimals0, decimals1)
	one := domain.NewDecimalFromInt(1)

	token0Stable := isLikelyStableToken(pool.Token0, decimals0)
	token1Stable := isLikelyStableToken(pool.Token1, decimals1)

	switch {
	case token1Stable && !token0Stable:
		return priceRatio, one, nil
	case token0Stable && !token1Stable:
		return one, one.Div(priceRatio), nil
	case token0Stable && token1Stable && priceRatio.GreaterThan(domain.MustDecimal("0.95")) && priceRatio.LessThan(domain.MustDecimal("1.05")):
		return one, one, nil
	default:
		return domain.ZeroDecimal(), domain.ZeroDecimal(), fmt.Errorf(
			"pool %s is unsupported for minimal live sizing: needs a stable-quoted base v3 pair",
			pool.ID,
		)
	}
}

func isLikelyStableToken(token domain.Address, decimals uint8) bool {
	if _, ok := knownBaseStableTokens[strings.ToLower(token.String())]; ok {
		return true
	}
	return decimals == 6
}

func priceRatioFromTick(tick int, decimals0, decimals1 uint8) domain.Decimal {
	price := domain.NewDecimalFromFloat(math.Pow(1.0001, float64(tick)))
	decimalDiff := int(decimals0) - int(decimals1)
	scale := scaleForDecimals(uint8(absInt(decimalDiff)))
	if decimalDiff > 0 {
		return price.Mul(scale)
	}
	if decimalDiff < 0 {
		return price.Div(scale)
	}
	return price
}

func scaleForDecimals(decimals uint8) domain.Decimal {
	return domain.MustDecimal("1" + strings.Repeat("0", int(decimals)))
}

func absInt(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func defaultOpenRange(currentTick int, tickSpacing int64) (int64, int64) {
	if tickSpacing <= 0 {
		tickSpacing = 1
	}
	width := int64(100)
	if tickSpacing*2 > width {
		width = tickSpacing * 2
	}
	lower := floorTickToSpacing(int64(currentTick)-width, tickSpacing)
	upper := ceilTickToSpacing(int64(currentTick)+width, tickSpacing)
	if lower == -100 && upper == 100 {
		return -500, 500
	}
	return lower, upper
}

func tickSpacingForFee(feeRaw uint32) int64 {
	switch feeRaw {
	case 100:
		return 1
	case 500:
		return 10
	case 3000:
		return 60
	case 10000:
		return 200
	default:
		return 60
	}
}

func floorTickToSpacing(tick, spacing int64) int64 {
	quotient := tick / spacing
	remainder := tick % spacing
	if remainder != 0 && tick < 0 {
		quotient--
	}
	return quotient * spacing
}

func ceilTickToSpacing(tick, spacing int64) int64 {
	quotient := tick / spacing
	remainder := tick % spacing
	if remainder != 0 && tick > 0 {
		quotient++
	}
	return quotient * spacing
}
