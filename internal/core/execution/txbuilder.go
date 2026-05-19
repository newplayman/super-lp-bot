package execution

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// TxBuilder builds unsigned transactions for position operations.
// It orchestrates the transaction construction workflow including:
//   - AddLiquidity: approve + add liquidity (two-step)
//   - RemoveLiquidity: remove + collect fees (exit sequence)
//   - Rebalance: remove + add in sequence
//   - CollectFees: collect accumulated fees
type TxBuilder struct {
	wallet ports.Wallet
	chain  ports.Chain
}

// NewTxBuilder creates a new TxBuilder instance.
func NewTxBuilder(wallet ports.Wallet, chain ports.Chain) *TxBuilder {
	return &TxBuilder{
		wallet: wallet,
		chain:  chain,
	}
}

// BuildAddLiquidityTx builds an add liquidity transaction for opening a position.
// For EVM chains, this builds a multicall or single add liquidity call.
// For Solana, this builds the appropriate instruction.
func (b *TxBuilder) BuildAddLiquidityTx(ctx context.Context, intent OpenIntent) (domain.UnsignedTx, error) {
	// Build the add liquidity transaction
	// The actual implementation depends on the chain type

	// Get the wallet address
	from := b.wallet.Address()

	// Build calldata based on chain
	// For now, we build a generic transaction structure
	tx := domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.Address{}, // Set by adapter
		Data:     b.buildAddLiquidityCalldata(intent),
		Value:    domain.MustDecimal("0"),
		Nonce:    0, // Will be set by nonce manager in real implementation
		Deadline: 0, // Will be set based on intent
		MinOut:   domain.MustDecimal("0"), // Set from intent simulation
	}

	return tx, nil
}

// BuildRemoveLiquidityTx builds a remove liquidity transaction for closing a position.
func (b *TxBuilder) BuildRemoveLiquidityTx(ctx context.Context, intent ExitIntent) (domain.UnsignedTx, error) {
	from := b.wallet.Address()

	tx := domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.Address{},
		Data:     b.buildRemoveLiquidityCalldata(intent),
		Value:    domain.MustDecimal("0"),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.MustDecimal("0"),
	}

	return tx, nil
}

// BuildRebalanceTxs builds remove and add transactions for rebalancing.
func (b *TxBuilder) BuildRebalanceTxs(ctx context.Context, intent RebalanceIntent) (removeTx, addTx domain.UnsignedTx, err error) {
	from := b.wallet.Address()

	// Build remove liquidity tx
	removeTx = domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.Address{},
		Data:     b.buildRemoveLiquidityCalldataForRebalance(intent),
		Value:    domain.MustDecimal("0"),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.MustDecimal("0"),
	}

	// Build add liquidity tx with new tick range
	addTx = domain.UnsignedTx{
		Chain:    intent.Chain,
		From:     from,
		To:       domain.Address{},
		Data:     b.buildAddLiquidityCalldataForRebalance(intent),
		Value:    domain.MustDecimal("0"),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.MustDecimal("0"),
	}

	return removeTx, addTx, nil
}

// BuildCollectFeesTx builds a collect fees transaction.
func (b *TxBuilder) BuildCollectFeesTx(ctx context.Context, positionID string) (domain.UnsignedTx, error) {
	from := b.wallet.Address()

	tx := domain.UnsignedTx{
		Chain:    domain.ChainID("base"), // Default, should be determined from position
		From:     from,
		To:       domain.Address{},
		Data:     b.buildCollectFeesCalldata(positionID),
		Value:    domain.MustDecimal("0"),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.MustDecimal("0"),
	}

	return tx, nil
}

// buildAddLiquidityCalldata builds the calldata for add liquidity.
// This is a placeholder that should be replaced with actual UniV3 calldata builder.
func (b *TxBuilder) buildAddLiquidityCalldata(intent OpenIntent) []byte {
	// TODO: Replace with actual UniV3 nonfungible position manager calldata
	// The calldata should encode:
	//   - mint: token ID (0 for new position)
	//   - recipient: wallet address
	//   - tickLower/tickUpper: position boundaries
	//   - amount0Desired/amount1Desired: token amounts
	return []byte{}
}

// buildRemoveLiquidityCalldata builds the calldata for remove liquidity.
func (b *TxBuilder) buildRemoveLiquidityCalldata(intent ExitIntent) []byte {
	// TODO: Replace with actual UniV3 nonfungible position manager calldata
	// The calldata should encode:
	//   - tokenId: position token ID
	//   - liquidity: amount to remove
	//   - deadline: transaction deadline
	//   - amount0Min/amount1Min: minimum amounts (slippage protection)
	return []byte{}
}

// buildRemoveLiquidityCalldataForRebalance builds remove calldata for rebalance.
func (b *TxBuilder) buildRemoveLiquidityCalldataForRebalance(intent RebalanceIntent) []byte {
	// TODO: Implement actual UniV3 calldata
	return []byte{}
}

// buildAddLiquidityCalldataForRebalance builds add calldata for rebalance with new ticks.
func (b *TxBuilder) buildAddLiquidityCalldataForRebalance(intent RebalanceIntent) []byte {
	// TODO: Implement actual UniV3 calldata with NewTickLower/NewTickUpper
	return []byte{}
}

// buildCollectFeesCalldata builds the calldata for collect fees.
func (b *TxBuilder) buildCollectFeesCalldata(positionID string) []byte {
	// TODO: Replace with actual UniV3 nonfungible position manager calldata
	// The calldata should encode:
	//   - tokenId: position token ID
	//   - recipient: wallet address
	//   - amount0Max/amount1Max: max amounts to collect (0 = collect all)
	return []byte{}
}

// SetNonce sets the nonce for a transaction.
// This is a helper method that should be called before signing.
func (b *TxBuilder) SetNonce(ctx context.Context, tx *domain.UnsignedTx) error {
	// Get nonce from chain
	// For EVM chains, use EVMChain interface
	if evmChain, ok := b.chain.(ports.EVMChain); ok {
		nonce, err := evmChain.PendingNonceAt(ctx, tx.From)
		if err != nil {
			return fmt.Errorf("failed to get nonce: %w", err)
		}
		tx.Nonce = nonce
	}
	return nil
}

// SetDeadline sets the deadline for a transaction.
func (b *TxBuilder) SetDeadline(tx *domain.UnsignedTx, deadline int64) {
	tx.Deadline = deadline
}