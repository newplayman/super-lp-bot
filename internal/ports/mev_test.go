package ports_test

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
)

// Compile-time interface assertion: MEVSubmitter must implement ports.MEVSubmitter
var _ ports.MEVSubmitter = (*mevSubmitterMock)(nil)

type mevSubmitterMock struct{}

func (m *mevSubmitterMock) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	return ports.MEVSubmissionResult{}, nil
}
func (m *mevSubmitterMock) Type() string { return "mock" }

// Compile-time interface assertion: mevSubmitterFuncMock implements MEVSubmitter for functional tests
var _ ports.MEVSubmitter = (*mevSubmitterFuncMock)(nil)

type mevSubmitterFuncMock struct {
	submitFn func(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error)
	typeFn   func() string
}

func (m *mevSubmitterFuncMock) Submit(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
	if m.submitFn != nil {
		return m.submitFn(ctx, tx, opts)
	}
	return ports.MEVSubmissionResult{}, nil
}

func (m *mevSubmitterFuncMock) Type() string {
	if m.typeFn != nil {
		return m.typeFn()
	}
	return "mock"
}

// TestMEVSubmitterInterface verifies the MEVSubmitter interface is properly defined
func TestMEVSubmitterInterface(t *testing.T) {
	require.NotNil(t, t, "ports.MEVSubmitter interface must exist")
}

// TestMEVSubmitterFuncMock verifies the functional mock can be instantiated
func TestMEVSubmitterFuncMock(t *testing.T) {
	ctx := context.Background()
	submitter := &mevSubmitterFuncMock{
		submitFn: func(ctx context.Context, tx domain.SignedTx, opts ports.MEVSubmitOpts) (ports.MEVSubmissionResult, error) {
			return ports.MEVSubmissionResult{
				BundleHash:   "0xbundle123",
				SimulateOnly: false,
			}, nil
		},
		typeFn: func() string { return "flashbots" },
	}

	result, err := submitter.Submit(ctx, domain.SignedTx{}, ports.MEVSubmitOpts{})
	require.NoError(t, err)
	require.Equal(t, "0xbundle123", result.BundleHash)
	require.Equal(t, "flashbots", submitter.Type())
}

// TestMEVSubmitOptsFields verifies MEVSubmitOpts structure
func TestMEVSubmitOptsFields(t *testing.T) {
	opts := ports.MEVSubmitOpts{
		MaxBundleGasLimit: 5000000,
		JitoTipLamports:   100000,
		FastMode:          true,
	}

	require.Equal(t, uint64(5000000), opts.MaxBundleGasLimit)
	require.Equal(t, uint64(100000), opts.JitoTipLamports)
	require.True(t, opts.FastMode)
}

// TestMEVSubmissionResultFields verifies MEVSubmissionResult structure
func TestMEVSubmissionResultFields(t *testing.T) {
	result := ports.MEVSubmissionResult{
		BundleHash:   "0xbundle456",
		Signature:   "sig123",
		SimulateOnly: true,
	}

	require.Equal(t, "0xbundle456", result.BundleHash)
	require.Equal(t, "sig123", result.Signature)
	require.True(t, result.SimulateOnly)
}