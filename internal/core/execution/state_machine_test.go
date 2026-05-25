package execution

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestValidatePositionTransition_Valid(t *testing.T) {
	validTransitions := []struct {
		from, to domain.PositionStatus
	}{
		{domain.StatusIntended, domain.StatusApproved},
		{domain.StatusIntended, domain.StatusRejected},
		{domain.StatusApproved, domain.StatusOpening},
		{domain.StatusOpening, domain.StatusOpen},
		{domain.StatusOpening, domain.StatusRejected},
		{domain.StatusOpening, domain.StatusExitFailed},
		{domain.StatusOpen, domain.StatusExiting},
		{domain.StatusOpen, domain.StatusManual},
		{domain.StatusExiting, domain.StatusClosed},
		{domain.StatusExiting, domain.StatusExitFailed},
		{domain.StatusExitFailed, domain.StatusManual},
		{domain.StatusExitFailed, domain.StatusExiting},
	}

	for _, tt := range validTransitions {
		t.Run(string(tt.from)+"_to_"+string(tt.to), func(t *testing.T) {
			if !ValidatePositionTransition(tt.from, tt.to) {
				t.Errorf("ValidatePositionTransition(%s, %s) = false, want true", tt.from, tt.to)
			}
		})
	}
}

func TestValidatePositionTransition_Invalid(t *testing.T) {
	invalidTransitions := []struct {
		from, to domain.PositionStatus
		desc     string
	}{
		{domain.StatusIntended, domain.StatusOpen, "skip from intended to open"},
		{domain.StatusIntended, domain.StatusClosed, "skip to closed"},
		{domain.StatusApproved, domain.StatusOpen, "skip approved to open"},
		{domain.StatusApproved, domain.StatusRejected, "approved cannot go back to rejected"},
		{domain.StatusRejected, domain.StatusApproved, "rejected is terminal"},
		{domain.StatusRejected, domain.StatusOpening, "rejected cannot transition"},
		{domain.StatusOpening, domain.StatusApproved, "opening cannot go back"},
		{domain.StatusOpening, domain.StatusExiting, "must go to open first"},
		{domain.StatusOpen, domain.StatusApproved, "open cannot go back"},
		{domain.StatusOpen, domain.StatusOpening, "open cannot go back to opening"},
		{domain.StatusExiting, domain.StatusOpen, "exiting cannot go back to open"},
		{domain.StatusExiting, domain.StatusApproved, "exiting cannot skip"},
		{domain.StatusClosed, domain.StatusOpen, "closed is terminal"},
		{domain.StatusClosed, domain.StatusExiting, "closed is terminal"},
		{domain.StatusExitFailed, domain.StatusOpen, "exitFailed cannot skip to open"},
		{domain.StatusExitFailed, domain.StatusApproved, "exitFailed cannot go back"},
		{domain.StatusManual, domain.StatusOpen, "manual is terminal"},
		{domain.StatusManual, domain.StatusExiting, "manual is terminal"},
	}

	for _, tt := range invalidTransitions {
		t.Run(tt.desc, func(t *testing.T) {
			if ValidatePositionTransition(tt.from, tt.to) {
				t.Errorf("ValidatePositionTransition(%s, %s) = true, want false: %s", tt.from, tt.to, tt.desc)
			}
		})
	}
}

func TestValidateTxTransition_Valid(t *testing.T) {
	validTransitions := []struct {
		from, to domain.TxStatus
	}{
		{domain.TxBuilt, domain.TxSubmittedPrivate},
		{domain.TxBuilt, domain.TxBroadcast},
		{domain.TxBuilt, domain.TxFailed},
		{domain.TxSubmittedPrivate, domain.TxMined},
		{domain.TxSubmittedPrivate, domain.TxBroadcast},
		{domain.TxSubmittedPrivate, domain.TxStuck},
		{domain.TxSubmittedPrivate, domain.TxFailed},
		{domain.TxBroadcast, domain.TxMined},
		{domain.TxBroadcast, domain.TxStuck},
		{domain.TxBroadcast, domain.TxReverted},
		{domain.TxBroadcast, domain.TxReorged},
		{domain.TxMined, domain.TxConfirmed},
		{domain.TxMined, domain.TxReverted},
		{domain.TxMined, domain.TxReorged},
		{domain.TxStuck, domain.TxMined},
		{domain.TxStuck, domain.TxRFBBumped},
		{domain.TxStuck, domain.TxFailed},
		{domain.TxRFBBumped, domain.TxMined},
		{domain.TxRFBBumped, domain.TxStuck},
		{domain.TxRFBBumped, domain.TxFailed},
		{domain.TxReverted, domain.TxBroadcast},
		{domain.TxReverted, domain.TxFailed},
		{domain.TxReorged, domain.TxBroadcast},
		{domain.TxReorged, domain.TxFailed},
	}

	for _, tt := range validTransitions {
		t.Run(string(tt.from)+"_to_"+string(tt.to), func(t *testing.T) {
			if !ValidateTxTransition(tt.from, tt.to) {
				t.Errorf("ValidateTxTransition(%s, %s) = false, want true", tt.from, tt.to)
			}
		})
	}
}

func TestValidateTxTransition_Invalid(t *testing.T) {
	invalidTransitions := []struct {
		from, to domain.TxStatus
		desc     string
	}{
		{domain.TxBuilt, domain.TxMined, "skip to mined"},
		{domain.TxBuilt, domain.TxConfirmed, "skip to confirmed"},
		{domain.TxSubmittedPrivate, domain.TxConfirmed, "private submit must still confirm on-chain"},
		{domain.TxBroadcast, domain.TxConfirmed, "must go through mined"},
		{domain.TxBroadcast, domain.TxBuilt, "cannot go back to built"},
		{domain.TxConfirmed, domain.TxMined, "confirmed is terminal"},
		{domain.TxConfirmed, domain.TxFailed, "confirmed is terminal"},
		{domain.TxConfirmed, domain.TxBroadcast, "confirmed is terminal"},
		{domain.TxStuck, domain.TxBroadcast, "stuck must use RBF"},
		{domain.TxStuck, domain.TxConfirmed, "stuck cannot go to confirmed directly"},
		{domain.TxRFBBumped, domain.TxBroadcast, "cannot go back to broadcast"},
		{domain.TxFailed, domain.TxBroadcast, "failed is terminal"},
		{domain.TxFailed, domain.TxMined, "failed is terminal"},
		{domain.TxReverted, domain.TxMined, "reverted cannot skip to mined"},
		{domain.TxReverted, domain.TxConfirmed, "reverted cannot skip to confirmed"},
		{domain.TxReorged, domain.TxMined, "reorged cannot skip to mined"},
	}

	for _, tt := range invalidTransitions {
		t.Run(tt.desc, func(t *testing.T) {
			if ValidateTxTransition(tt.from, tt.to) {
				t.Errorf("ValidateTxTransition(%s, %s) = true, want false: %s", tt.from, tt.to, tt.desc)
			}
		})
	}
}

func TestIsTerminalStatus(t *testing.T) {
	tests := []struct {
		status domain.PositionStatus
		expect bool
	}{
		{domain.StatusIntended, false},
		{domain.StatusApproved, false},
		{domain.StatusRejected, true},
		{domain.StatusOpening, false},
		{domain.StatusOpen, false},
		{domain.StatusExiting, false},
		{domain.StatusClosed, true},
		{domain.StatusExitFailed, false},
		{domain.StatusManual, true},
	}

	for _, tt := range tests {
		t.Run(string(tt.status), func(t *testing.T) {
			if got := IsTerminalStatus(tt.status); got != tt.expect {
				t.Errorf("IsTerminalStatus(%s) = %v, want %v", tt.status, got, tt.expect)
			}
		})
	}
}

func TestIsTerminalTxStatus(t *testing.T) {
	tests := []struct {
		status domain.TxStatus
		expect bool
	}{
		{domain.TxBuilt, false},
		{domain.TxSubmittedPrivate, false},
		{domain.TxBroadcast, false},
		{domain.TxMined, false},
		{domain.TxConfirmed, true},
		{domain.TxStuck, false},
		{domain.TxRFBBumped, false},
		{domain.TxFailed, true},
		{domain.TxReverted, false},
		{domain.TxReorged, false},
	}

	for _, tt := range tests {
		t.Run(string(tt.status), func(t *testing.T) {
			if got := IsTerminalTxStatus(tt.status); got != tt.expect {
				t.Errorf("IsTerminalTxStatus(%s) = %v, want %v", tt.status, got, tt.expect)
			}
		})
	}
}

func TestValidPositionTransitions(t *testing.T) {
	tests := []struct {
		from   domain.PositionStatus
		expect []domain.PositionStatus
	}{
		{domain.StatusIntended, []domain.PositionStatus{domain.StatusApproved, domain.StatusRejected}},
		{domain.StatusApproved, []domain.PositionStatus{domain.StatusOpening}},
		{domain.StatusRejected, nil},
		{domain.StatusOpening, []domain.PositionStatus{domain.StatusOpen, domain.StatusRejected, domain.StatusExitFailed}},
		{domain.StatusOpen, []domain.PositionStatus{domain.StatusExiting, domain.StatusManual}},
		{domain.StatusExiting, []domain.PositionStatus{domain.StatusClosed, domain.StatusExitFailed}},
		{domain.StatusClosed, nil},
		{domain.StatusExitFailed, []domain.PositionStatus{domain.StatusManual, domain.StatusExiting}},
		{domain.StatusManual, nil},
	}

	for _, tt := range tests {
		t.Run(string(tt.from), func(t *testing.T) {
			got := ValidPositionTransitions(tt.from)
			if len(got) != len(tt.expect) {
				t.Errorf("ValidPositionTransitions(%s) returned %d items, want %d", tt.from, len(got), len(tt.expect))
				return
			}
			for i, v := range got {
				if v != tt.expect[i] {
					t.Errorf("ValidPositionTransitions(%s)[%d] = %s, want %s", tt.from, i, v, tt.expect[i])
				}
			}
		})
	}
}

func TestValidTxTransitions(t *testing.T) {
	tests := []struct {
		from   domain.TxStatus
		expect []domain.TxStatus
	}{
		{domain.TxBuilt, []domain.TxStatus{domain.TxSubmittedPrivate, domain.TxBroadcast, domain.TxFailed}},
		{domain.TxSubmittedPrivate, []domain.TxStatus{domain.TxMined, domain.TxBroadcast, domain.TxStuck, domain.TxFailed, domain.TxReverted, domain.TxReorged}},
		{domain.TxBroadcast, []domain.TxStatus{domain.TxMined, domain.TxStuck, domain.TxReverted, domain.TxReorged}},
		{domain.TxMined, []domain.TxStatus{domain.TxConfirmed, domain.TxReverted, domain.TxReorged}},
		{domain.TxConfirmed, nil},
		{domain.TxStuck, []domain.TxStatus{domain.TxMined, domain.TxRFBBumped, domain.TxFailed}},
		{domain.TxRFBBumped, []domain.TxStatus{domain.TxMined, domain.TxStuck, domain.TxFailed}},
		{domain.TxFailed, nil},
		{domain.TxReverted, []domain.TxStatus{domain.TxBroadcast, domain.TxFailed}},
		{domain.TxReorged, []domain.TxStatus{domain.TxBroadcast, domain.TxFailed}},
	}

	for _, tt := range tests {
		t.Run(string(tt.from), func(t *testing.T) {
			got := ValidTxTransitions(tt.from)
			if len(got) != len(tt.expect) {
				t.Errorf("ValidTxTransitions(%s) returned %d items, want %d", tt.from, len(got), len(tt.expect))
				return
			}
			for i, v := range got {
				if v != tt.expect[i] {
					t.Errorf("ValidTxTransitions(%s)[%d] = %s, want %s", tt.from, i, v, tt.expect[i])
				}
			}
		})
	}
}

func TestDomainMethodsStillWork(t *testing.T) {
	// Ensure domain.CanTransitionTo methods still work correctly
	// This is a compatibility check with existing domain types

	// Position status transitions
	if !domain.StatusIntended.CanTransitionTo(domain.StatusApproved) {
		t.Error("domain.StatusIntended.CanTransitionTo(domain.StatusApproved) should be true")
	}
	if domain.StatusRejected.CanTransitionTo(domain.StatusApproved) {
		t.Error("domain.StatusRejected.CanTransitionTo(domain.StatusApproved) should be false")
	}

	// Tx status transitions
	if !domain.TxBuilt.CanTransitionTo(domain.TxBroadcast) {
		t.Error("domain.TxBuilt.CanTransitionTo(domain.TxBroadcast) should be true")
	}
	if domain.TxConfirmed.CanTransitionTo(domain.TxMined) {
		t.Error("domain.TxConfirmed.CanTransitionTo(domain.TxMined) should be false")
	}
}
