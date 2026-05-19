package domain

import "math/big"

// SimulationResult represents the outcome of a transaction simulation.
type SimulationResult struct {
	// Success indicates whether the transaction completed without revert.
	Success bool

	// GasUsed is the gas consumed by the simulation.
	GasUsed uint64

	// GasPrice is the gas price used (EVM only).
	GasPrice *big.Int

	// ReturnData is the raw return data from the simulation.
	// For successful calls, this contains the encoded results.
	// For reverts, this contains the revert reason.
	ReturnData []byte

	// OutputAmounts contains the actual amounts received from the simulation.
	// For add liquidity: token amounts added to position.
	// For remove/exit: tokens reclaimed.
	// For swaps: output token amounts.
	OutputAmounts []TokenAmount

	// BlockRef is the block state used for this simulation.
	BlockRef BlockRef

	// Error is the simulation error string, if any.
	// When Success is false, this field contains the revert reason.
	Error string
}

// IsRevert returns true if the simulation succeeded but transaction reverted.
func (r SimulationResult) IsRevert() bool {
	return r.Error != ""
}