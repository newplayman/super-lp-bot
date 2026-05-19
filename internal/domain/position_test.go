package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestPositionStatus_ValidTransitions(t *testing.T) {
	require.True(t, domain.StatusIntended.CanTransitionTo(domain.StatusApproved))
	require.True(t, domain.StatusIntended.CanTransitionTo(domain.StatusRejected))
	require.False(t, domain.StatusIntended.CanTransitionTo(domain.StatusOpen))
	require.False(t, domain.StatusIntended.CanTransitionTo(domain.StatusClosed))

	require.True(t, domain.StatusOpen.CanTransitionTo(domain.StatusExiting))
	require.True(t, domain.StatusOpen.CanTransitionTo(domain.StatusManual))
	require.False(t, domain.StatusOpen.CanTransitionTo(domain.StatusApproved))
}

func TestPositionStatus_TerminalStates(t *testing.T) {
	// These states should have no valid next transitions
	terminal := []domain.PositionStatus{
		domain.StatusRejected,
		domain.StatusClosed,
		domain.StatusManual,
	}
	for _, s := range terminal {
		require.Empty(t, domain.ValidTransitions[s], "%s should be terminal", s)
	}
}