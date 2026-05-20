package postgres

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

var (
	_ ports.TxRepo       = (*TxRepoStub)(nil)
	_ ports.PositionRepo = (*PositionRepoStub)(nil)
	_ ports.PoolRepo     = (*PoolRepoStub)(nil)
	_ ports.ConfigSnap   = (*ConfigSnapStub)(nil)
	_ ports.RiskRepo     = (*RiskRepoStub)(nil)
	_ ports.ReconRepo    = (*ReconRepoStub)(nil)
	_ ports.LedgerRepo   = (*LedgerRepoStub)(nil)
)

type (
	TxRepoStub       struct{}
	PositionRepoStub struct{}
	PoolRepoStub     struct{}
	ConfigSnapStub   struct{}
	RiskRepoStub     struct{}
	ReconRepoStub    struct{}
	LedgerRepoStub   struct{}
)

func (*TxRepoStub) UpsertTx(context.Context, domain.SignedTx) error                       { return nil }
func (*TxRepoStub) GetTxByHash(context.Context, domain.ChainID, string) (domain.SignedTx, error) {
	return domain.SignedTx{}, ports.ErrTxNotFound
}
func (*TxRepoStub) ListTxsByStatus(context.Context, domain.ChainID, domain.TxStatus) ([]domain.SignedTx, error) {
	return nil, nil
}
func (*TxRepoStub) UpdateTxStatus(context.Context, domain.ChainID, string, domain.TxStatus, *domain.BlockRef) error {
	return nil
}
func (*TxRepoStub) ListPendingTxs(context.Context, domain.ChainID) ([]domain.SignedTx, error) { return nil, nil }
func (*TxRepoStub) ListStuckTxs(context.Context, domain.ChainID, int64) ([]domain.SignedTx, error) {
	return nil, nil
}
func (*TxRepoStub) IncrementRFBAttempts(context.Context, domain.ChainID, string) error { return nil }
func (*TxRepoStub) GetRFBAttempts(context.Context, domain.ChainID, string) (int, error) { return 0, nil }

func (*PositionRepoStub) Save(context.Context, *domain.Position) error                                                    { return nil }
func (*PositionRepoStub) FindByID(context.Context, string) (*domain.Position, error)                                     { return nil, nil }
func (*PositionRepoStub) FindByPoolAndStatus(context.Context, string, domain.PositionStatus) ([]*domain.Position, error) { return nil, nil }
func (*PositionRepoStub) FindByChainAndStatus(context.Context, domain.ChainID, domain.PositionStatus) ([]*domain.Position, error) {
	return nil, nil
}
func (*PositionRepoStub) UpdateStatus(context.Context, string, domain.PositionStatus) error { return nil }
func (*PositionRepoStub) Snapshot(context.Context, string) ([]*domain.Position, error) { return nil, nil }

func (*PoolRepoStub) UpsertPool(context.Context, ports.PoolWithScore) error                                        { return nil }
func (*PoolRepoStub) GetPool(context.Context, string) (domain.Pool, error)                                         { return domain.Pool{}, ports.ErrPoolNotFound }
func (*PoolRepoStub) ListPools(context.Context, ports.PoolFilter) ([]domain.Pool, error)                            { return nil, nil }
func (*PoolRepoStub) GetScoreHistory(context.Context, string, int) ([]ports.PoolScoreSnapshot, error)                { return nil, nil }
func (*PoolRepoStub) UpsertAuditVerdict(context.Context, string, domain.AuditVerdict, float64) error                 { return nil }

func (*ConfigSnapStub) AppendSnapshot(context.Context, ports.ConfigSnapshot) error                          { return nil }
func (*ConfigSnapStub) GetLatestSnapshot(context.Context, domain.Env) (ports.ConfigSnapshot, error)        { return ports.ConfigSnapshot{}, ports.ErrConfigSnapNotFound }
func (*ConfigSnapStub) GetPreviousSnapshot(context.Context, domain.Env) (ports.ConfigSnapshot, error)      { return ports.ConfigSnapshot{}, ports.ErrConfigSnapNotFound }
func (*ConfigSnapStub) ListSnapshots(context.Context, ports.ConfigSnapFilter) ([]ports.ConfigSnapshot, error) { return nil, nil }

func (*RiskRepoStub) AppendRiskEvent(context.Context, ports.RiskEvent) error                                              { return nil }
func (*RiskRepoStub) ListRiskEvents(context.Context, ports.RiskEventFilter) ([]ports.RiskEvent, error)                   { return nil, nil }
func (*RiskRepoStub) GetKillState(context.Context) (ports.KillState, error)                                              { return ports.KillState{}, nil }
func (*RiskRepoStub) UpsertKillState(context.Context, ports.KillState) error                                             { return nil }

func (*ReconRepoStub) AppendReconciliationLog(context.Context, ports.ReconciliationLog) error                                    { return nil }
func (*ReconRepoStub) ListReconciliationLogs(context.Context, ports.ReconLogFilter) ([]ports.ReconciliationLog, error)          { return nil, nil }
func (*ReconRepoStub) GetLatestReconciliation(context.Context, domain.ChainID) (ports.ReconciliationLog, error)                  { return ports.ReconciliationLog{}, ports.ErrReconLogNotFound }

func (*LedgerRepoStub) Append(context.Context, ports.LedgerEntry) (ports.LedgerEntry, error)                                              { return ports.LedgerEntry{}, nil }
func (*LedgerRepoStub) ByPosition(context.Context, string) ([]ports.LedgerEntry, error)                                                { return nil, nil }
func (*LedgerRepoStub) ByPositionAndKind(context.Context, string, ports.LedgerEntryKind) ([]ports.LedgerEntry, error)                { return nil, nil }
func (*LedgerRepoStub) AggregateByKind(context.Context, string) (map[ports.LedgerEntryKind]domain.Decimal, error)                     { return nil, nil }
func (*LedgerRepoStub) LatestBlock(context.Context) (*domain.BlockRef, error)                                                        { return nil, nil }