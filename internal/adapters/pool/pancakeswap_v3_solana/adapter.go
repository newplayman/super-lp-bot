// Package pancakeswap_v3_solana provides the PancakeSwap V3 Solana pool adapter implementation.
package pancakeswap_v3_solana

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// Adapter implements ports.V3Pool for PancakeSwap V3 on Solana.
// This is a stub implementation that formalizes the protocol boundary for
// upcoming add-liquidity and position-management work.
type Adapter struct {
	poolID   string
	chain    domain.ChainID
	protocol string
	token0   domain.Address
	token1   domain.Address
	feeBPS   uint
	tier     domain.Tier
}

func (a *Adapter) PoolID() string        { return a.poolID }
func (a *Adapter) Chain() domain.ChainID { return a.chain }
func (a *Adapter) Protocol() string      { return a.protocol }
func (a *Adapter) Token0() domain.Address { return a.token0 }
func (a *Adapter) Token1() domain.Address { return a.token1 }
func (a *Adapter) FeeBPS() uint          { return a.feeBPS }
func (a *Adapter) Tier() domain.Tier     { return a.tier }

func (a *Adapter) GetState(ctx interface{}) (domain.PoolState, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

func (a *Adapter) Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

func (a *Adapter) BuildAddLiquidity(ctx interface{}, params ports.AddLiquidityParams) (domain.UnsignedTx, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

func (a *Adapter) BuildRemoveLiquidity(ctx interface{}, positionID string, liquidity domain.Decimal) (domain.UnsignedTx, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

func (a *Adapter) BuildCollectFees(ctx interface{}, positionID string) (domain.UnsignedTx, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

func (a *Adapter) BuildSwap(ctx interface{}, params ports.SwapParams) (domain.UnsignedTx, error) {
	panic("not implemented: pancakeswap_v3_solana adapter")
}

// Compile-time interface assertion.
var _ ports.V3Pool = (*Adapter)(nil)
