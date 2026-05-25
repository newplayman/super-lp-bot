package domain

// ExecutionIntentStatus tracks the lifecycle of a concrete execution action.
type ExecutionIntentStatus string

const (
	IntentStatusIntended         ExecutionIntentStatus = "intended"
	IntentStatusReserved         ExecutionIntentStatus = "reserved"
	IntentStatusSigned           ExecutionIntentStatus = "signed"
	IntentStatusSubmittedPrivate ExecutionIntentStatus = "submitted_private"
	IntentStatusBroadcast        ExecutionIntentStatus = "broadcast"
	IntentStatusMined            ExecutionIntentStatus = "mined"
	IntentStatusConfirmed        ExecutionIntentStatus = "confirmed"
	IntentStatusReconciled       ExecutionIntentStatus = "reconciled"
	IntentStatusStuck            ExecutionIntentStatus = "stuck"
	IntentStatusFailed           ExecutionIntentStatus = "failed"
)

type ExecutionIntent struct {
	ID                 string
	Mode               string
	Chain              ChainID
	PoolID             string
	PositionID         string
	Action             string
	Status             ExecutionIntentStatus
	IdempotencyKey     string
	UnsignedTxHash     string
	SignedTxHash       string
	TxHash             string
	Reason             string
	RiskSnapshotJSON   string
	SizingSnapshotJSON string
	DecisionTraceID    string
	CreatedAt          int64
	UpdatedAt          int64
}
