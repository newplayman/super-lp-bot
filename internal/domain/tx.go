package domain

// TxStatus represents the state of a transaction.
type TxStatus string

const (
	TxBuilt            TxStatus = "built"
	TxSubmittedPrivate TxStatus = "submitted_private"
	TxBroadcast        TxStatus = "broadcast"
	TxMined            TxStatus = "mined"
	TxConfirmed        TxStatus = "confirmed"
	TxStuck            TxStatus = "stuck"
	TxRFBBumped        TxStatus = "rbf_bumped"
	TxFailed           TxStatus = "failed"
	TxReverted         TxStatus = "reverted"
	TxReorged          TxStatus = "reorged"
)

// TxValidTransitions maps current status → allowed next statuses.
var TxValidTransitions = map[TxStatus][]TxStatus{
	TxBuilt:            {TxSubmittedPrivate, TxBroadcast, TxFailed},
	TxSubmittedPrivate: {TxMined, TxBroadcast, TxStuck, TxFailed, TxReverted, TxReorged},
	TxBroadcast:        {TxMined, TxStuck, TxReverted, TxReorged},
	TxMined:            {TxConfirmed, TxReverted, TxReorged},
	TxConfirmed:        {},
	TxStuck:            {TxRFBBumped, TxFailed},
	TxRFBBumped:        {TxMined, TxStuck, TxFailed}, // stuck again possible
	TxFailed:           {},
	TxReverted:         {TxBroadcast, TxFailed}, // retry possible
	TxReorged:          {TxBroadcast, TxFailed}, // rebroadcast or give up
}

// CanTransitionTo checks if a transition from current → next is valid.
func (s TxStatus) CanTransitionTo(next TxStatus) bool {
	allowed := TxValidTransitions[s]
	for _, a := range allowed {
		if a == next {
			return true
		}
	}
	return false
}

// MaxRBFAttempts returns the maximum RBF attempts allowed.
func MaxRBFAttempts() int { return 3 }

// UnsignedTx represents a transaction before signing.
type UnsignedTx struct {
	ID       string  // Unique identifier for the transaction
	Chain    ChainID // Target chain
	From     Address // Sender address
	To       Address // Recipient address
	Data     []byte  // Calldata
	Value    Decimal // ETH value
	Nonce    uint64  // Transaction nonce
	Deadline int64   // Deadline timestamp
	MinOut   Decimal // Minimum output amount
}

// SignedTx is a signed transaction.
type SignedTx struct {
	UnsignedTx
	Signature   []byte
	Hash        string
	RFBAttempts int      // Tracks RFB attempt count for this tx
	Status      TxStatus // Current transaction status
}
