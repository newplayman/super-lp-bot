package execution

import (
	"github.com/lpbot/lpbot/internal/domain"
)

// Position state transition validation map.
// Maps each position status to its valid next states.
var positionValidTransitions = map[domain.PositionStatus][]domain.PositionStatus{
	domain.StatusIntended:   {domain.StatusApproved, domain.StatusRejected},
	domain.StatusApproved:   {domain.StatusOpening},
	domain.StatusRejected:   {},
	domain.StatusOpening:    {domain.StatusOpen, domain.StatusExitFailed},
	domain.StatusOpen:       {domain.StatusExiting, domain.StatusManual},
	domain.StatusExiting:    {domain.StatusClosed, domain.StatusExitFailed},
	domain.StatusClosed:     {},
	domain.StatusExitFailed: {domain.StatusManual, domain.StatusExiting},
	domain.StatusManual:     {},
}

// Tx state transition validation map.
// Maps each tx status to its valid next states.
var txValidTransitions = map[domain.TxStatus][]domain.TxStatus{
	domain.TxBuilt:     {domain.TxBroadcast, domain.TxFailed},
	domain.TxBroadcast: {domain.TxMined, domain.TxStuck, domain.TxReverted, domain.TxReorged},
	domain.TxMined:     {domain.TxConfirmed, domain.TxReverted, domain.TxReorged},
	domain.TxConfirmed: {},
	domain.TxStuck:     {domain.TxRFBBumped, domain.TxFailed},
	domain.TxRFBBumped: {domain.TxMined, domain.TxStuck, domain.TxFailed},
	domain.TxFailed:    {},
	domain.TxReverted:  {domain.TxBroadcast, domain.TxFailed},
	domain.TxReorged:   {domain.TxBroadcast, domain.TxFailed},
}

// ValidatePositionTransition checks if a position state transition is valid.
// Returns true if the transition from 'from' to 'to' is allowed.
func ValidatePositionTransition(from, to domain.PositionStatus) bool {
	validNextStates, exists := positionValidTransitions[from]
	if !exists {
		return false
	}
	for _, valid := range validNextStates {
		if valid == to {
			return true
		}
	}
	return false
}

// ValidateTxTransition checks if a tx state transition is valid.
// Returns true if the transition from 'from' to 'to' is allowed.
func ValidateTxTransition(from, to domain.TxStatus) bool {
	validNextStates, exists := txValidTransitions[from]
	if !exists {
		return false
	}
	for _, valid := range validNextStates {
		if valid == to {
			return true
		}
	}
	return false
}

// IsTerminalStatus returns true if the position status is a terminal state
// (no further transitions are allowed).
func IsTerminalStatus(status domain.PositionStatus) bool {
	terminalStatuses := []domain.PositionStatus{
		domain.StatusRejected,
		domain.StatusClosed,
		domain.StatusManual,
	}
	for _, t := range terminalStatuses {
		if status == t {
			return true
		}
	}
	return false
}

// IsTerminalTxStatus returns true if the tx status is a terminal state
// (no further transitions are allowed).
func IsTerminalTxStatus(status domain.TxStatus) bool {
	terminalStatuses := []domain.TxStatus{
		domain.TxConfirmed,
		domain.TxFailed,
	}
	for _, t := range terminalStatuses {
		if status == t {
			return true
		}
	}
	return false
}

// ValidPositionTransitions returns the list of valid next states for a position status.
func ValidPositionTransitions(from domain.PositionStatus) []domain.PositionStatus {
	if transitions, ok := positionValidTransitions[from]; ok {
		result := make([]domain.PositionStatus, len(transitions))
		copy(result, transitions)
		return result
	}
	return nil
}

// ValidTxTransitions returns the list of valid next states for a tx status.
func ValidTxTransitions(from domain.TxStatus) []domain.TxStatus {
	if transitions, ok := txValidTransitions[from]; ok {
		result := make([]domain.TxStatus, len(transitions))
		copy(result, transitions)
		return result
	}
	return nil
}