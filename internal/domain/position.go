package domain

// PositionStatus represents the lifecycle state of a position.
type PositionStatus string

const (
	StatusIntended   PositionStatus = "intended"
	StatusApproved   PositionStatus = "approved"
	StatusRejected   PositionStatus = "rejected"
	StatusOpening    PositionStatus = "opening"
	StatusOpen       PositionStatus = "open"
	StatusExiting    PositionStatus = "exiting"
	StatusClosed     PositionStatus = "closed"
	StatusExitFailed PositionStatus = "exit_failed"
	StatusManual     PositionStatus = "manual"
)

// ValidTransitions maps current status → allowed next statuses.
var ValidTransitions = map[PositionStatus][]PositionStatus{
	StatusIntended:   {StatusApproved, StatusRejected},
	StatusApproved:   {StatusOpening},
	StatusRejected:   {},
	StatusOpening:    {StatusOpen, StatusExitFailed},
	StatusOpen:       {StatusExiting, StatusManual},
	StatusExiting:    {StatusClosed, StatusExitFailed},
	StatusClosed:     {},
	StatusExitFailed: {StatusManual, StatusExiting},
	StatusManual:     {},
}

// CanTransitionTo checks if a transition from current → next is valid.
func (s PositionStatus) CanTransitionTo(next PositionStatus) bool {
	for _, allowed := range ValidTransitions[s] {
		if allowed == next {
			return true
		}
	}
	return false
}

// Position represents an LP position.
type Position struct {
	ID        string
	TokenID   string
	PoolID    string
	Chain     ChainID
	Status    PositionStatus
	Tier      Tier
	AmountUSD Decimal // position size in USD

	// V3 specific
	TickLower int64
	TickUpper int64

	// Timestamps
	OpenedAt int64
	ClosedAt int64
}
