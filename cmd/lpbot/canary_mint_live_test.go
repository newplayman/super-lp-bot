//go:build live

package main

import (
	"context"
	"errors"
	"math/big"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/internal/domain"
)

type fakeCanaryMintState struct {
	reserved       map[string]domain.PositionStatus
	reserveErr     error
	recordedTx     []domain.TxStatus
	recordedEvents []string
}

func (s *fakeCanaryMintState) ReserveOpeningPosition(_ context.Context, pos *domain.Position) error {
	if s.reserveErr != nil {
		return s.reserveErr
	}
	if s.reserved == nil {
		s.reserved = make(map[string]domain.PositionStatus)
	}
	s.reserved[pos.ID] = pos.Status
	return nil
}

func (s *fakeCanaryMintState) UpdatePositionStatus(_ context.Context, positionID string, status domain.PositionStatus) error {
	if s.reserved == nil {
		s.reserved = make(map[string]domain.PositionStatus)
	}
	s.reserved[positionID] = status
	return nil
}

func (s *fakeCanaryMintState) RecordSignedTx(_ context.Context, _ domain.SignedTx, status domain.TxStatus) error {
	s.recordedTx = append(s.recordedTx, status)
	return nil
}

func (s *fakeCanaryMintState) Record(_ context.Context, event canaryEvent) error {
	s.recordedEvents = append(s.recordedEvents, event.Stage)
	return nil
}

type fakeCanaryWallet struct {
	signCalled bool
}

func (w *fakeCanaryWallet) Address() domain.Address {
	return domain.MustParseAddress("0x1111111111111111111111111111111111111111")
}

func (w *fakeCanaryWallet) Sign(_ context.Context, tx domain.UnsignedTx) (domain.SignedTx, error) {
	w.signCalled = true
	return domain.SignedTx{
		UnsignedTx: tx,
		Hash:       "0xsigned",
		Signature:  []byte{1, 2, 3},
	}, nil
}

type fakeCanaryBroadcaster struct {
	sendCalled    bool
	state         *fakeCanaryMintState
	reservationID string
}

func (b *fakeCanaryBroadcaster) Send(_ context.Context, _ domain.SignedTx) error {
	b.sendCalled = true
	if b.state == nil {
		return errors.New("missing state")
	}
	if status := b.state.reserved[b.reservationID]; status != domain.StatusIntended {
		return errors.New("reservation missing before send")
	}
	return nil
}

func (b *fakeCanaryBroadcaster) CallCount() int64 { return 0 }

func TestSubmitReservedCanaryMint_ReservationHappensBeforeBroadcast(t *testing.T) {
	state := &fakeCanaryMintState{}
	wallet := &fakeCanaryWallet{}
	broadcaster := &fakeCanaryBroadcaster{state: state, reservationID: "pos-1"}
	reservation := &domain.Position{
		ID:     "pos-1",
		PoolID: "pool-1",
		Chain:  domain.ChainBase,
		Status: domain.StatusIntended,
	}

	signed, err := submitReservedCanaryMint(context.Background(), state, wallet, broadcaster, reservation, domain.UnsignedTx{
		ID:    "tx-1",
		Chain: domain.ChainBase,
		From:  wallet.Address(),
	}, canaryMintSubmissionInput{
		Pool:          domain.Pool{ID: "pool-1", Chain: domain.ChainBase},
		PositionID:    "pos-1",
		Wallet:        wallet.Address(),
		AmountUSD:     domain.MustDecimal("5"),
		RequiredUSDC:  bigZero(),
		RequiredWETH:  bigZero(),
		GasEstimate:   21000,
		Confirmations: 0,
	})
	require.NoError(t, err)
	require.True(t, wallet.signCalled)
	require.True(t, broadcaster.sendCalled)
	require.Equal(t, domain.TxBroadcast, signed.Status)
	require.Equal(t, domain.StatusOpening, state.reserved["pos-1"])
}

func TestSubmitReservedCanaryMint_DuplicateReservationBlocksSignAndBroadcast(t *testing.T) {
	state := &fakeCanaryMintState{reserveErr: errors.New("duplicate active position")}
	wallet := &fakeCanaryWallet{}
	broadcaster := &fakeCanaryBroadcaster{state: state, reservationID: "pos-dup"}
	reservation := &domain.Position{
		ID:     "pos-dup",
		PoolID: "pool-1",
		Chain:  domain.ChainBase,
		Status: domain.StatusIntended,
	}

	_, err := submitReservedCanaryMint(context.Background(), state, wallet, broadcaster, reservation, domain.UnsignedTx{
		ID:    "tx-dup",
		Chain: domain.ChainBase,
		From:  wallet.Address(),
	}, canaryMintSubmissionInput{
		Pool:          domain.Pool{ID: "pool-1", Chain: domain.ChainBase},
		PositionID:    "pos-dup",
		Wallet:        wallet.Address(),
		AmountUSD:     domain.MustDecimal("5"),
		RequiredUSDC:  bigZero(),
		RequiredWETH:  bigZero(),
		GasEstimate:   21000,
		Confirmations: 0,
	})
	require.Error(t, err)
	require.False(t, wallet.signCalled)
	require.False(t, broadcaster.sendCalled)
}

func TestValidateLiveSchemaState_MissingUniqueIndexBlocksStartup(t *testing.T) {
	err := validateLiveSchemaState(map[string]bool{
		"positions":                         true,
		"transactions":                      true,
		"canary_events":                     true,
		"pnl_ledger":                        true,
		"shadow_decision_trace":             true,
		"idx_positions_one_active_per_pool": false,
	})
	require.Error(t, err)
	require.Contains(t, err.Error(), "idx_positions_one_active_per_pool")
}

func bigZero() *big.Int { return new(big.Int) }
