// Package aerodrome provides the Aerodrome pool adapter implementation.
package aerodrome

import (
	"context"
	"fmt"
	"math/big"

	"github.com/ethereum/go-ethereum/common"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// Protocol name for Aerodrome
const ProtocolName = "aerodrome"

// Aerodrome V2 Router addresses
const (
	RouterV2Address   = "0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2"
	FactoryV2Address = "0x420DD7b1D89364d57d6EEA33300755E7d0fF6794"
)

// Function selectors (first 4 bytes of keccak256 hash)
var (
	addLiquiditySelector       = [4]byte{0xb9, 0x5c, 0xac, 0x29} // addLiquidity
	removeLiquiditySelector   = [4]byte{0x0c, 0xfe, 0x81, 0xc8}  // removeLiquidity
	claimFeesSelector        = [4]byte{0x9f, 0xf3, 0xe9, 0xfc}   // claimFees
	swapSelector             = [4]byte{0x38, 0xb2, 0xa2, 0x1d}   // swap
	quoteAddLiquiditySelector = [4]byte{0xf2, 0x8f, 0x82, 0x05}   // quoteAddLiquidity
)

// Adapter implements ports.V3Pool for Aerodrome V2 on Base chain.
type Adapter struct {
	poolID   string
	chain    domain.ChainID
	protocol string
	token0   domain.Address
	token1   domain.Address
	feeBPS   uint
	tier     domain.Tier
	router   domain.Address
}

// NewAdapter creates a new Aerodrome pool adapter.
func NewAdapter(poolID, token0, token1 string, feeBPS uint, tier domain.Tier) *Adapter {
	return &Adapter{
		poolID:   poolID,
		chain:    domain.ChainBase,
		protocol: ProtocolName,
		token0:   domain.MustParseAddress(token0),
		token1:   domain.MustParseAddress(token1),
		feeBPS:   feeBPS,
		tier:     tier,
		router:   domain.MustParseAddress(RouterV2Address),
	}
}

// NewAdapterWithRouter creates a new Aerodrome pool adapter with custom router.
func NewAdapterWithRouter(poolID, token0, token1, routerAddress string, feeBPS uint, tier domain.Tier) *Adapter {
	return &Adapter{
		poolID:   poolID,
		chain:    domain.ChainBase,
		protocol: ProtocolName,
		token0:   domain.MustParseAddress(token0),
		token1:   domain.MustParseAddress(token1),
		feeBPS:   feeBPS,
		tier:     tier,
		router:   domain.MustParseAddress(routerAddress),
	}
}

func (a *Adapter) PoolID() string                                      { return a.poolID }
func (a *Adapter) Chain() domain.ChainID                               { return a.chain }
func (a *Adapter) Protocol() string                                    { return a.protocol }
func (a *Adapter) Token0() domain.Address                             { return a.token0 }
func (a *Adapter) Token1() domain.Address                             { return a.token1 }
func (a *Adapter) FeeBPS() uint                                       { return a.feeBPS }
func (a *Adapter) Tier() domain.Tier                                  { return a.tier }
func (a *Adapter) Router() domain.Address                             { return a.router }

func (a *Adapter) GetState(ctx interface{}) (domain.PoolState, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	_ = c
	return domain.PoolState{
		BlockRef:    domain.BlockRef{Chain: domain.ChainBase},
		SqrtPriceX96: big.NewInt(1),
		Tick:        0,
		Liquidity:   big.NewInt(0),
	}, nil
}

func (a *Adapter) Quote(ctx interface{}, amount domain.Decimal, zeroForOne bool) (domain.TokenAmount, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	feeMultiplier := decimal.NewFromFloat(1.0).Sub(
		decimal.NewFromInt(int64(a.feeBPS)).Div(decimal.NewFromInt(10000)),
	)
	outputAmount := amount.Mul(feeMultiplier)

	var outputToken domain.Token
	if zeroForOne {
		outputToken = domain.Token{Address: a.token1, Symbol: "", Decimals: 18, Chain: domain.ChainBase}
	} else {
		outputToken = domain.Token{Address: a.token0, Symbol: "", Decimals: 18, Chain: domain.ChainBase}
	}
	_ = c
	return domain.TokenAmount{Token: outputToken, Amount: outputAmount}, nil
}

func (a *Adapter) BuildAddLiquidity(ctx interface{}, params ports.AddLiquidityParams) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	if params.Deadline == 0 {
		panic("deadline is required (invariant #4)")
	}
	data := buildAddLiquidityCalldata(a.poolID, a.token0, a.token1, params)
	tx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		From:     params.Recipient,
		To:       a.router,
		Data:     data,
		Value:    domain.Decimal{},
		Deadline: params.Deadline,
		MinOut:   params.MinAmount1,
	}
	_ = c
	return tx, nil
}

func (a *Adapter) BuildRemoveLiquidity(ctx interface{}, positionID string, liquidity domain.Decimal) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	data := buildRemoveLiquidityCalldata(a.poolID, a.token0, a.token1, liquidity)
	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		To:    a.router,
		Data:  data,
	}
	_ = c
	return tx, nil
}

func (a *Adapter) BuildCollectFees(ctx interface{}, positionID string) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	data := buildClaimFeesCalldata(positionID)
	tx := domain.UnsignedTx{
		Chain: domain.ChainBase,
		To:    domain.MustParseAddress(positionID),
		Data:  data,
	}
	_ = c
	return tx, nil
}

func (a *Adapter) BuildSwap(ctx interface{}, params ports.SwapParams) (domain.UnsignedTx, error) {
	c, ok := ctx.(context.Context)
	if !ok {
		c = context.Background()
	}
	if params.Deadline == 0 {
		panic("deadline is required (invariant #4)")
	}
	data, err := buildSwapCalldata(params, a.token0, a.token1)
	if err != nil {
		return domain.UnsignedTx{}, fmt.Errorf("failed to build swap calldata: %w", err)
	}
	tx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		From:     params.Recipient,
		To:       a.router,
		Data:     data,
		Value:    domain.Decimal{},
		Deadline: params.Deadline,
		MinOut:   params.MinOut,
	}
	_ = c
	return tx, nil
}

// buildAddLiquidityCalldata encodes addLiquidity(address,address,address,uint256,uint256,address,uint256,uint256)
func buildAddLiquidityCalldata(pool string, token0, token1 domain.Address, params ports.AddLiquidityParams) []byte {
	data := make([]byte, 4+32*8)
	copy(data[0:4], addLiquiditySelector[:])

	copy(data[4:36], common.LeftPadBytes(token0.Bytes(), 32))
	copy(data[36:68], common.LeftPadBytes(token1.Bytes(), 32))
	copy(data[68:100], common.LeftPadBytes(common.HexToAddress(pool).Bytes(), 32))
	copy(data[100:132], common.LeftPadBytes(params.Amount0.BigInt().Bytes(), 32))
	copy(data[132:164], common.LeftPadBytes(params.Amount1.BigInt().Bytes(), 32))
	copy(data[164:196], common.LeftPadBytes(params.Recipient.Bytes(), 32))
	copy(data[196:228], common.LeftPadBytes(params.MinAmount0.BigInt().Bytes(), 32))
	copy(data[228:260], common.LeftPadBytes(params.MinAmount1.BigInt().Bytes(), 32))

	return data
}

// buildRemoveLiquidityCalldata encodes removeLiquidity(address,address,address,uint256,address)
func buildRemoveLiquidityCalldata(pool string, token0, token1 domain.Address, liquidity domain.Decimal) []byte {
	data := make([]byte, 4+32*5)
	copy(data[0:4], removeLiquiditySelector[:])

	copy(data[4:36], common.LeftPadBytes(token0.Bytes(), 32))
	copy(data[36:68], common.LeftPadBytes(token1.Bytes(), 32))
	copy(data[68:100], common.LeftPadBytes(common.HexToAddress(pool).Bytes(), 32))
	copy(data[100:132], common.LeftPadBytes(liquidity.BigInt().Bytes(), 32))
	copy(data[132:164], common.LeftPadBytes(token0.Bytes(), 32)) // recipient placeholder

	return data
}

// buildClaimFeesCalldata encodes claimFees(address)
func buildClaimFeesCalldata(gauge string) []byte {
	data := make([]byte, 4+32)
	copy(data[0:4], claimFeesSelector[:])
	copy(data[4:36], common.LeftPadBytes(common.HexToAddress(gauge).Bytes(), 32))
	return data
}

// buildSwapCalldata encodes swap(uint256,address,address,address)
func buildSwapCalldata(params ports.SwapParams, token0, token1 domain.Address) ([]byte, error) {
	data := make([]byte, 4+32*4)
	copy(data[0:4], swapSelector[:])

	copy(data[4:36], common.LeftPadBytes(params.Amount.BigInt().Bytes(), 32))

	var tokenIn, tokenOut domain.Address
	if params.ZeroForOne {
		tokenIn = token0
		tokenOut = token1
	} else {
		tokenIn = token1
		tokenOut = token0
	}
	copy(data[36:68], common.LeftPadBytes(tokenIn.Bytes(), 32))
	copy(data[68:100], common.LeftPadBytes(tokenOut.Bytes(), 32))
	copy(data[100:132], common.LeftPadBytes(params.Recipient.Bytes(), 32))

	return data, nil
}

var _ ports.V3Pool = (*Adapter)(nil)