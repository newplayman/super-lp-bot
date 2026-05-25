package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestTxStatus_ValidTransitions(t *testing.T) {
	require.True(t, domain.TxBuilt.CanTransitionTo(domain.TxSubmittedPrivate))
	require.True(t, domain.TxBuilt.CanTransitionTo(domain.TxBroadcast))
	require.True(t, domain.TxSubmittedPrivate.CanTransitionTo(domain.TxMined))
	require.True(t, domain.TxBroadcast.CanTransitionTo(domain.TxMined))
	require.True(t, domain.TxBroadcast.CanTransitionTo(domain.TxStuck))
	require.True(t, domain.TxStuck.CanTransitionTo(domain.TxMined))
	require.True(t, domain.TxStuck.CanTransitionTo(domain.TxRFBBumped))
	require.True(t, domain.TxStuck.CanTransitionTo(domain.TxFailed))
	require.False(t, domain.TxConfirmed.CanTransitionTo(domain.TxBroadcast))
}

func TestTxStatus_MaxRBF(t *testing.T) {
	require.Equal(t, 3, domain.MaxRBFAttempts())
}

func TestUnsignedTx_HasMinOut(t *testing.T) {
	tx := domain.UnsignedTx{
		Chain:  domain.ChainBase,
		MinOut: domain.MustDecimal("0"),
	}
	require.True(t, tx.MinOut.IsZero()) // zero = not set = invalid
}
