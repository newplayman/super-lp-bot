package execution

import (
	"context"
	"errors"
	"math/big"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/common"

	npmabi "github.com/lpbot/lpbot/internal/adapters/chain/base/abi"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	ErrTickInvalid       = errors.New("tickLower must be less than tickUpper")
	ErrDeadlineExpired   = errors.New("deadline must be in the future")
	ErrSlippageTooHigh   = errors.New("slippageBps must be less than 10000 (100%)")
	ErrZeroAmountDesired = errors.New("amount desired must be greater than 0")
	ErrTokenIDInvalid    = errors.New("token id must be a valid base-10 integer")
	ErrRebalancePending  = errors.New("rebalance tx building is not implemented")
)

// TxBuilder builds unsigned transactions for position operations.
// It orchestrates the transaction construction workflow including:
//   - AddLiquidity: approve + add liquidity (two-step)
//   - RemoveLiquidity: remove + collect fees (exit sequence)
//   - Rebalance: remove + add in sequence
//   - CollectFees: collect accumulated fees
type TxBuilder struct {
	wallet  ports.Wallet
	chain   ports.Chain
	npmAddr common.Address // NonfungiblePositionManager address from config
}

// NPMConfig holds the NonfungiblePositionManager address per chain.
type NPMConfig struct {
	Base string // Base chain NPM address
}

type uniswapV3MintParams struct {
	Token0         common.Address `abi:"token0"`
	Token1         common.Address `abi:"token1"`
	Fee            *big.Int       `abi:"fee"`
	TickLower      *big.Int       `abi:"tickLower"`
	TickUpper      *big.Int       `abi:"tickUpper"`
	Amount0Desired *big.Int       `abi:"amount0Desired"`
	Amount1Desired *big.Int       `abi:"amount1Desired"`
	Amount0Min     *big.Int       `abi:"amount0Min"`
	Amount1Min     *big.Int       `abi:"amount1Min"`
	Recipient      common.Address `abi:"recipient"`
	Deadline       *big.Int       `abi:"deadline"`
}

// NewTxBuilder creates a new TxBuilder instance.
func NewTxBuilder(wallet ports.Wallet, chain ports.Chain, npmConfig NPMConfig) *TxBuilder {
	var npmAddr common.Address
	if npmConfig.Base != "" {
		npmAddr = common.HexToAddress(npmConfig.Base)
	}
	return &TxBuilder{
		wallet:  wallet,
		chain:   chain,
		npmAddr: npmAddr,
	}
}

// BuildAddLiquidityTx builds an add liquidity transaction for opening a position.
// For EVM chains, this builds a mint call to the NonfungiblePositionManager.
func (b *TxBuilder) BuildAddLiquidityTx(ctx context.Context, intent OpenIntent) (domain.UnsignedTx, error) {
	from := b.wallet.Address()

	calldata, to, err := b.BuildMintCalldata(intent)
	if err != nil {
		return domain.UnsignedTx{}, err
	}

	tx := domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.MustParseAddress(to.Hex()),
		Data:     calldata,
		Value:    domain.ZeroDecimal(),
		Nonce:    0, // Will be set by nonce manager
		Deadline: intent.Deadline,
		MinOut:   domain.NewDecimalFromInt(1),
	}

	return tx, nil
}

// BuildRemoveLiquidityTx builds a remove liquidity transaction for closing a position.
func (b *TxBuilder) BuildRemoveLiquidityTx(ctx context.Context, intent ExitIntent) (domain.UnsignedTx, error) {
	from := b.wallet.Address()

	calldata, to, err := b.BuildDecreaseLiquidityCalldata(DecreaseLiquidityIntent{
		TokenId:     intent.TokenId,
		Liquidity:   intent.Liquidity,
		SlippageBps: intent.SlippageBps,
		Deadline:    intent.Deadline,
		Amount0Min:  intent.Amount0Min,
		Amount1Min:  intent.Amount1Min,
	})
	if err != nil {
		return domain.UnsignedTx{}, err
	}

	tx := domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.MustParseAddress(to.Hex()),
		Data:     calldata,
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: intent.Deadline,
		MinOut:   domain.NewDecimalFromInt(1),
	}

	return tx, nil
}

// BuildRebalanceTxs builds remove and add transactions for rebalancing.
func (b *TxBuilder) BuildRebalanceTxs(ctx context.Context, intent RebalanceIntent) (removeTx, addTx domain.UnsignedTx, err error) {
	_ = ctx
	_ = intent
	return removeTx, addTx, ErrRebalancePending
}

// BuildCollectFeesTx builds a collect fees transaction.
func (b *TxBuilder) BuildCollectFeesTx(ctx context.Context, positionID string) (domain.UnsignedTx, error) {
	from := b.wallet.Address()

	calldata, to, err := b.BuildCollectCalldata(CollectIntent{
		TokenId:    positionID,
		Recipient:  from,
		Amount0Max: domain.ZeroDecimal(),
		Amount1Max: domain.ZeroDecimal(),
	})
	if err != nil {
		return domain.UnsignedTx{}, err
	}

	tx := domain.UnsignedTx{
		Chain:    domain.ChainID("base"),
		From:     from,
		To:       domain.MustParseAddress(to.Hex()),
		Data:     calldata,
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.NewDecimalFromInt(1),
	}

	return tx, nil
}

// BuildMintCalldata builds calldata for minting a new LP position.
// It encodes the mint call using ABI packing and returns the target NPM address.
func (b *TxBuilder) BuildMintCalldata(intent OpenIntent) ([]byte, common.Address, error) {
	// Validate tick range
	if intent.TickLower >= intent.TickUpper {
		return nil, common.Address{}, ErrTickInvalid
	}

	// Validate deadline
	if intent.Deadline <= time.Now().Unix() {
		return nil, common.Address{}, ErrDeadlineExpired
	}

	// Validate slippage
	if intent.SlippageBps >= 10000 {
		return nil, common.Address{}, ErrSlippageTooHigh
	}

	// Calculate amountMin with slippage protection
	// amountMin = amountDesired * (1 - slippageBps/10000)
	amount0Desired := intent.Amount0.BigInt()
	amount1Desired := intent.Amount1.BigInt()

	amount0Min := calculateSlippageAmount(amount0Desired, intent.SlippageBps)
	amount1Min := calculateSlippageAmount(amount1Desired, intent.SlippageBps)

	// Validate amounts
	if amount0Min.Sign() == 0 && amount1Min.Sign() == 0 {
		return nil, common.Address{}, ErrZeroAmountDesired
	}

	params := uniswapV3MintParams{
		Token0:         common.HexToAddress(intent.Token0.String()),
		Token1:         common.HexToAddress(intent.Token1.String()),
		Fee:            new(big.Int).SetUint64(uint64(intent.Fee)),
		TickLower:      big.NewInt(intent.TickLower),
		TickUpper:      big.NewInt(intent.TickUpper),
		Amount0Desired: amount0Desired,
		Amount1Desired: amount1Desired,
		Amount0Min:     amount0Min,
		Amount1Min:     amount1Min,
		Recipient:      common.HexToAddress(intent.Recipient.String()),
		Deadline:       big.NewInt(intent.Deadline),
	}
	data, err := npmabi.NPMABI.Pack("mint", params)
	if err != nil {
		return nil, common.Address{}, err
	}

	return data, b.npmAddr, nil
}

// BuildIncreaseLiquidityCalldata builds calldata for increasing liquidity in an existing position.
func (b *TxBuilder) BuildIncreaseLiquidityCalldata(intent IncreaseLiquidityIntent) ([]byte, common.Address, error) {
	// Validate deadline
	if intent.Deadline <= time.Now().Unix() {
		return nil, common.Address{}, ErrDeadlineExpired
	}

	// Validate amounts
	if intent.Amount0.Sign() == 0 && intent.Amount1.Sign() == 0 {
		return nil, common.Address{}, ErrZeroAmountDesired
	}

	// Calculate amountMin with slippage protection
	amount0Desired := intent.Amount0.BigInt()
	amount1Desired := intent.Amount1.BigInt()
	amount0Min := calculateSlippageAmount(amount0Desired, intent.SlippageBps)
	amount1Min := calculateSlippageAmount(amount1Desired, intent.SlippageBps)

	// Parse token ID
	tokenId, err := parseTokenID(intent.TokenId)
	if err != nil {
		return nil, common.Address{}, err
	}

	// Pack the increaseLiquidity call
	data, err := npmabi.NPMABI.Pack("increaseLiquidity",
		tokenId,
		amount0Desired,
		amount1Desired,
		amount0Min,
		amount1Min,
		big.NewInt(intent.Deadline),
	)
	if err != nil {
		return nil, common.Address{}, err
	}

	return data, b.npmAddr, nil
}

// BuildDecreaseLiquidityCalldata builds calldata for decreasing liquidity in an existing position.
func (b *TxBuilder) BuildDecreaseLiquidityCalldata(intent DecreaseLiquidityIntent) ([]byte, common.Address, error) {
	// Validate deadline
	if intent.Deadline <= time.Now().Unix() {
		return nil, common.Address{}, ErrDeadlineExpired
	}

	// Calculate amountMin with slippage protection
	// For decrease, we use the intent's Amount0Min/Amount1Min directly
	amount0Min := intent.Amount0Min.BigInt()
	amount1Min := intent.Amount1Min.BigInt()

	// If slippage is provided, recalculate
	if intent.SlippageBps > 0 {
		liquidity := intent.Liquidity.BigInt()
		amount0Min = calculateSlippageAmount(liquidity, intent.SlippageBps)
		amount1Min = calculateSlippageAmount(liquidity, intent.SlippageBps)
	}

	// Validate that at least one amountMin is non-zero (slippage protection)
	if amount0Min.Sign() == 0 && amount1Min.Sign() == 0 {
		return nil, common.Address{}, ErrZeroAmountDesired
	}

	// Parse token ID
	tokenId, err := parseTokenID(intent.TokenId)
	if err != nil {
		return nil, common.Address{}, err
	}

	// Parse liquidity
	liquidity := intent.Liquidity.BigInt()

	// Pack the decreaseLiquidity call
	data, err := npmabi.NPMABI.Pack("decreaseLiquidity",
		tokenId,
		liquidity,
		amount0Min,
		amount1Min,
		big.NewInt(intent.Deadline),
	)
	if err != nil {
		return nil, common.Address{}, err
	}

	return data, b.npmAddr, nil
}

// BuildCollectCalldata builds calldata for collecting fees from a position.
func (b *TxBuilder) BuildCollectCalldata(intent CollectIntent) ([]byte, common.Address, error) {
	// Parse token ID
	tokenId, err := parseTokenID(intent.TokenId)
	if err != nil {
		return nil, common.Address{}, err
	}

	// For amount0Max/amount1Max, use max uint128 to collect all
	maxUint128 := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 128), big.NewInt(1))
	amount0Max := intent.Amount0Max.BigInt()
	amount1Max := intent.Amount1Max.BigInt()

	// If amounts are 0, use max to collect all
	if amount0Max.Sign() == 0 {
		amount0Max = maxUint128
	}
	if amount1Max.Sign() == 0 {
		amount1Max = maxUint128
	}

	// Pack the collect call
	data, err := npmabi.NPMABI.Pack("collect",
		tokenId,
		common.HexToAddress(intent.Recipient.String()),
		amount0Max,
		amount1Max,
	)
	if err != nil {
		return nil, common.Address{}, err
	}

	return data, b.npmAddr, nil
}

// BuildBurnCalldata builds calldata for burning a position NFT.
// Should only be called after liquidity has been fully removed (liquidity = 0).
func (b *TxBuilder) BuildBurnCalldata(intent BurnIntent) ([]byte, common.Address, error) {
	// Parse token ID
	tokenId, err := parseTokenID(intent.TokenId)
	if err != nil {
		return nil, common.Address{}, err
	}

	// Pack the burn call
	data, err := npmabi.NPMABI.Pack("burn", tokenId)
	if err != nil {
		return nil, common.Address{}, err
	}

	return data, b.npmAddr, nil
}

// calculateSlippageAmount computes: amount * (10000 - slippageBps) / 10000
func calculateSlippageAmount(amount *big.Int, slippageBps int64) *big.Int {
	if amount.Sign() == 0 {
		return big.NewInt(0)
	}
	result := new(big.Int).Sub(big.NewInt(10000), big.NewInt(slippageBps))
	result.Mul(amount, result)
	result.Div(result, big.NewInt(10000))
	return result
}

func parseTokenID(raw string) (*big.Int, error) {
	tokenID, ok := new(big.Int).SetString(strings.TrimSpace(raw), 10)
	if !ok || tokenID.Sign() < 0 {
		return nil, ErrTokenIDInvalid
	}
	return tokenID, nil
}

// SetNonce sets the nonce for a transaction.
// This is a helper method that should be called before signing.
func (b *TxBuilder) SetNonce(ctx context.Context, tx *domain.UnsignedTx) error {
	// Get nonce from chain
	// For EVM chains, use EVMChain interface
	if evmChain, ok := b.chain.(ports.EVMChain); ok {
		nonce, err := evmChain.PendingNonceAt(ctx, tx.From)
		if err != nil {
			return err
		}
		tx.Nonce = nonce
	}
	return nil
}

// SetDeadline sets the deadline for a transaction.
func (b *TxBuilder) SetDeadline(tx *domain.UnsignedTx, deadline int64) {
	tx.Deadline = deadline
}
