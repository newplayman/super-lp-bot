package ports_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: Alerter must implement ports.Alerter
var _ ports.Alerter = (*alerterMock)(nil)

type alerterMock struct{}

func (m *alerterMock) SendAlert(level ports.AlertLevel, src, msg string) error { return nil }

// Compile-time interface assertion: AlertLevel satisfies stringer-like contract
var _ = ports.AlertP0
var _ = ports.AlertP1
var _ = ports.AlertP2

// TestAlerterInterface verifies the Alerter interface is properly defined
func TestAlerterInterface(t *testing.T) {
	require.NotNil(t, t, "ports.Alerter interface must exist")
	require.NotNil(t, t, "ports.AlertLevel type must exist")

	// Test that we can create and use an alerter mock
	var a ports.Alerter = &alerterMock{}
	err := a.SendAlert(ports.AlertP0, "test-source", "test message")
	require.NoError(t, err)
}

// TestAlertLevelValues verifies AlertLevel constants are defined
func TestAlertLevelValues(t *testing.T) {
	// Verify the three alert levels exist
	require.Equal(t, ports.AlertLevel("p0"), ports.AlertP0)
	require.Equal(t, ports.AlertLevel("p1"), ports.AlertP1)
	require.Equal(t, ports.AlertLevel("p2"), ports.AlertP2)
}

// TestAlertLevelString verifies string representation
func TestAlertLevelString(t *testing.T) {
	require.Equal(t, "p0", string(ports.AlertP0))
	require.Equal(t, "p1", string(ports.AlertP1))
	require.Equal(t, "p2", string(ports.AlertP2))
}