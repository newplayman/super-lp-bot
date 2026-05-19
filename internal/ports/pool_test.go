package ports

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time interface compliance checks for V3Pool
func TestV3PoolInterface(t *testing.T) {
	var _ V3Pool = (*v3PoolNop)(nil)
}

// Compile-time interface compliance checks for V2Pool
func TestV2PoolInterface(t *testing.T) {
	var _ V2Pool = (*v2PoolNop)(nil)
}

// v3PoolNop is a no-op implementation for compile-time interface checks.
type v3PoolNop struct{}

func (v3PoolNop) PoolID() string                                     { return "" }
func (v3PoolNop) Chain() domain.ChainID                              { return "" }
func (v3PoolNop) Protocol() string                                   { return "" }
func (v3PoolNop) Token0() domain.Address                             { return domain.Address{} }
func (v3PoolNop) Token1() domain.Address                             { return domain.Address{} }
func (v3PoolNop) FeeBPS() uint                                       { return 0 }
func (v3PoolNop) Tier() domain.Tier                                  { return "" }
func (v3PoolNop) GetState(ctx interface{}) (domain.PoolState, error) { return domain.PoolState{}, nil }
func (v3PoolNop) Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error) {
	return domain.TokenAmount{}, nil
}
func (v3PoolNop) BuildAddLiquidity(ctx interface{}, params AddLiquidityParams) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (v3PoolNop) BuildRemoveLiquidity(ctx interface{}, positionID string, liquidity domain.Decimal) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (v3PoolNop) BuildCollectFees(ctx interface{}, positionID string) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (v3PoolNop) BuildSwap(ctx interface{}, params SwapParams) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}

// v2PoolNop is a no-op implementation for compile-time interface checks.
type v2PoolNop struct{}

func (v2PoolNop) PoolID() string                                     { return "" }
func (v2PoolNop) Chain() domain.ChainID                              { return "" }
func (v2PoolNop) Protocol() string                                   { return "" }
func (v2PoolNop) Token0() domain.Address                             { return domain.Address{} }
func (v2PoolNop) Token1() domain.Address                             { return domain.Address{} }
func (v2PoolNop) FeeBPS() uint                                       { return 0 }
func (v2PoolNop) Tier() domain.Tier                                  { return "" }
func (v2PoolNop) GetState(ctx interface{}) (domain.PoolState, error) { return domain.PoolState{}, nil }
func (v2PoolNop) Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error) {
	return domain.TokenAmount{}, nil
}
func (v2PoolNop) BuildAddLiquidity(ctx interface{}, params AddLiquidityParams) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (v2PoolNop) BuildRemoveLiquidity(ctx interface{}, params RemoveLiquidityParams) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
func (v2PoolNop) BuildSwap(ctx interface{}, params SwapParams) (domain.UnsignedTx, error) {
	return domain.UnsignedTx{}, nil
}
