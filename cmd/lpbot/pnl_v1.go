package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

type runtimeSQLTables struct {
	db                     *sql.DB
	dialect                string
	pnlLedgerTable         string
	positionMarksTable     string
	portfolioSnapshotTable string
	shadowOutcomeTable     string
}

type pnlLedgerRecord struct {
	ID                string
	PositionID        string
	PoolID            string
	Kind              string
	Amount            domain.Decimal
	TokenSymbol       string
	Chain             domain.ChainID
	BlockNumber       uint64
	BlockHash         string
	BlockTime         int64
	TxHash            string
	Source            string
	PositionValueUSD  domain.Decimal
	FeeCollectedUSD   domain.Decimal
	FeeUncollectedUSD domain.Decimal
	GasUSD            domain.Decimal
	ILUSD             domain.Decimal
	LVRUSD            domain.Decimal
	NetPnLUSD         domain.Decimal
	TraceID           string
}

type positionMarkRecord struct {
	ID                string
	PositionID        string
	PoolID            string
	Chain             domain.ChainID
	TokenID           string
	Status            domain.PositionStatus
	AmountUSD         domain.Decimal
	PositionValueUSD  domain.Decimal
	FeeCollectedUSD   domain.Decimal
	FeeUncollectedUSD domain.Decimal
	GasUSD            domain.Decimal
	ILUSD             domain.Decimal
	LVRUSD            domain.Decimal
	NetPnLUSD         domain.Decimal
	Source            string
	MetadataJSON      string
	MarkTime          int64
	CreatedAt         int64
}

func newRuntimeSQLTables(store ports.Store) (*runtimeSQLTables, error) {
	if store == nil {
		return nil, fmt.Errorf("store is nil")
	}
	dbHolder, ok := any(store).(interface{ DB() *sql.DB })
	if !ok || dbHolder.DB() == nil {
		return nil, fmt.Errorf("store does not expose DB")
	}
	tables := &runtimeSQLTables{
		db:                     dbHolder.DB(),
		dialect:                "postgres",
		pnlLedgerTable:         "pnl_ledger",
		positionMarksTable:     "position_marks",
		portfolioSnapshotTable: "portfolio_snapshots",
		shadowOutcomeTable:     "shadow_outcome_labels",
	}
	if prefixed, ok := any(store).(interface{ Prefix() string }); ok {
		prefix := strings.TrimSpace(prefixed.Prefix())
		if prefix != "" {
			tables.dialect = "sqlite"
			tables.pnlLedgerTable = prefix + "_pnl_ledger"
			tables.positionMarksTable = prefix + "_position_marks"
			tables.portfolioSnapshotTable = prefix + "_portfolio_snapshots"
		}
	}
	return tables, nil
}

func (t *runtimeSQLTables) insertPnLLedger(ctx context.Context, record pnlLedgerRecord) error {
	if t == nil || t.db == nil {
		return fmt.Errorf("pnl ledger store not configured")
	}
	if strings.TrimSpace(record.ID) == "" {
		record.ID = fmt.Sprintf("%s:%s:%d", strings.TrimSpace(record.Source), record.PositionID, record.BlockTime)
	}
	if strings.TrimSpace(record.TokenSymbol) == "" {
		record.TokenSymbol = "USD"
	}

	switch t.dialect {
	case "sqlite":
		_, err := t.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT OR IGNORE INTO %s (
				id, position_id, pool_id, kind, amount, token_symbol, chain, block_number, block_hash, block_time,
				tx_hash, source, position_value_usd, fee_collected_usd, fee_uncollected_usd, gas_usd,
				il_usd, lvr_usd, net_pnl_usd, trace_id
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`, t.pnlLedgerTable),
			record.ID, record.PositionID, record.PoolID, record.Kind, record.Amount.String(), record.TokenSymbol,
			string(record.Chain), record.BlockNumber, record.BlockHash, record.BlockTime,
			record.TxHash, record.Source, record.PositionValueUSD.String(), record.FeeCollectedUSD.String(),
			record.FeeUncollectedUSD.String(), record.GasUSD.String(), record.ILUSD.String(), record.LVRUSD.String(),
			record.NetPnLUSD.String(), record.TraceID,
		)
		return err
	default:
		_, err := t.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, position_id, pool_id, kind, amount, token_symbol, chain, block_number, block_hash, block_time,
				tx_hash, source, position_value_usd, fee_collected_usd, fee_uncollected_usd, gas_usd,
				il_usd, lvr_usd, net_pnl_usd, trace_id
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
			ON CONFLICT (id) DO NOTHING
		`, t.pnlLedgerTable),
			record.ID, record.PositionID, record.PoolID, record.Kind, record.Amount.String(), record.TokenSymbol,
			domainChainToInt(record.Chain), record.BlockNumber, record.BlockHash, record.BlockTime,
			record.TxHash, record.Source, record.PositionValueUSD.String(), record.FeeCollectedUSD.String(),
			record.FeeUncollectedUSD.String(), record.GasUSD.String(), record.ILUSD.String(), record.LVRUSD.String(),
			record.NetPnLUSD.String(), record.TraceID,
		)
		return err
	}
}

func (t *runtimeSQLTables) insertPositionMark(ctx context.Context, record positionMarkRecord) error {
	if t == nil || t.db == nil {
		return fmt.Errorf("position mark store not configured")
	}
	if strings.TrimSpace(record.ID) == "" {
		record.ID = fmt.Sprintf("mark:%s:%d", record.PositionID, record.MarkTime)
	}
	if record.MetadataJSON == "" {
		record.MetadataJSON = "{}"
	}

	switch t.dialect {
	case "sqlite":
		_, err := t.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, position_id, pool_id, chain, token_id, status, amount_usd, position_value_usd,
				fee_collected_usd, fee_uncollected_usd, gas_usd, il_usd, lvr_usd, net_pnl_usd,
				source, metadata_json, mark_time, created_at
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`, t.positionMarksTable),
			record.ID, record.PositionID, record.PoolID, string(record.Chain), record.TokenID, string(record.Status),
			record.AmountUSD.String(), record.PositionValueUSD.String(), record.FeeCollectedUSD.String(),
			record.FeeUncollectedUSD.String(), record.GasUSD.String(), record.ILUSD.String(), record.LVRUSD.String(),
			record.NetPnLUSD.String(), record.Source, record.MetadataJSON, record.MarkTime, record.CreatedAt,
		)
		return err
	default:
		_, err := t.db.ExecContext(ctx, fmt.Sprintf(`
			INSERT INTO %s (
				id, position_id, pool_id, chain, token_id, status, amount_usd, position_value_usd,
				fee_collected_usd, fee_uncollected_usd, gas_usd, il_usd, lvr_usd, net_pnl_usd,
				source, metadata_json, mark_time, created_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16::jsonb, $17, $18)
			ON CONFLICT (id) DO NOTHING
		`, t.positionMarksTable),
			record.ID, record.PositionID, record.PoolID, string(record.Chain), record.TokenID, string(record.Status),
			record.AmountUSD.String(), record.PositionValueUSD.String(), record.FeeCollectedUSD.String(),
			record.FeeUncollectedUSD.String(), record.GasUSD.String(), record.ILUSD.String(), record.LVRUSD.String(),
			record.NetPnLUSD.String(), record.Source, record.MetadataJSON, record.MarkTime, record.CreatedAt,
		)
		return err
	}
}

func (t *runtimeSQLTables) loadLatestPositionMark(ctx context.Context, positionID string) (positionMarkRecord, bool, error) {
	if t == nil || t.db == nil {
		return positionMarkRecord{}, false, fmt.Errorf("position mark store not configured")
	}
	query := fmt.Sprintf(`
		SELECT id, position_id, pool_id, chain, COALESCE(token_id, ''), status, amount_usd, position_value_usd,
		       fee_collected_usd, fee_uncollected_usd, gas_usd, il_usd, lvr_usd, net_pnl_usd,
		       source, COALESCE(metadata_json, '{}'), mark_time, created_at
		FROM %s
		WHERE position_id = %s
		ORDER BY mark_time DESC, created_at DESC
		LIMIT 1
	`, t.positionMarksTable, t.placeholder(1))
	var record positionMarkRecord
	var chain string
	err := t.db.QueryRowContext(ctx, query, positionID).Scan(
		&record.ID, &record.PositionID, &record.PoolID, &chain, &record.TokenID, &record.Status,
		stringScanner(&record.AmountUSD), stringScanner(&record.PositionValueUSD), stringScanner(&record.FeeCollectedUSD),
		stringScanner(&record.FeeUncollectedUSD), stringScanner(&record.GasUSD), stringScanner(&record.ILUSD),
		stringScanner(&record.LVRUSD), stringScanner(&record.NetPnLUSD), &record.Source, &record.MetadataJSON,
		&record.MarkTime, &record.CreatedAt,
	)
	if err == sql.ErrNoRows {
		return positionMarkRecord{}, false, nil
	}
	if err != nil {
		return positionMarkRecord{}, false, err
	}
	record.Chain = domain.ChainID(chain)
	return record, true, nil
}

func (t *runtimeSQLTables) sumRealizedPnL(ctx context.Context) (domain.Decimal, error) {
	if t == nil || t.db == nil {
		return domain.ZeroDecimal(), fmt.Errorf("pnl ledger store not configured")
	}
	query := fmt.Sprintf(`SELECT COALESCE(SUM(CAST(net_pnl_usd AS NUMERIC)), 0)::text FROM %s WHERE kind = %s`, t.pnlLedgerTable, t.placeholder(1))
	if t.dialect == "sqlite" {
		query = fmt.Sprintf(`SELECT COALESCE(SUM(CAST(net_pnl_usd AS NUMERIC)), 0) FROM %s WHERE kind = ?`, t.pnlLedgerTable)
	}
	var total string
	if err := t.db.QueryRowContext(ctx, query, "settle").Scan(&total); err != nil {
		return domain.ZeroDecimal(), err
	}
	return decimalFromStringSafe(total), nil
}

func (t *runtimeSQLTables) loadPositionRealizedTotals(ctx context.Context, positionID string) (feeCollectedUSD, gasUSD, netPnLUSD domain.Decimal, err error) {
	if t == nil || t.db == nil {
		return domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), fmt.Errorf("pnl ledger store not configured")
	}
	query := fmt.Sprintf(`
		SELECT
			COALESCE(SUM(CAST(fee_collected_usd AS NUMERIC)), 0)::text,
			COALESCE(SUM(CAST(gas_usd AS NUMERIC)), 0)::text,
			COALESCE(SUM(CAST(net_pnl_usd AS NUMERIC)), 0)::text
		FROM %s
		WHERE position_id = %s AND source <> %s AND kind <> %s
	`, t.pnlLedgerTable, t.placeholder(1), t.placeholder(2), t.placeholder(3))
	if t.dialect == "sqlite" {
		query = fmt.Sprintf(`
			SELECT
				COALESCE(SUM(CAST(fee_collected_usd AS NUMERIC)), 0),
				COALESCE(SUM(CAST(gas_usd AS NUMERIC)), 0),
				COALESCE(SUM(CAST(net_pnl_usd AS NUMERIC)), 0)
			FROM %s
			WHERE position_id = ? AND source <> ? AND kind <> ?
		`, t.pnlLedgerTable)
	}
	var feeText, gasText, netText string
	if err := t.db.QueryRowContext(ctx, query, positionID, "position_mark", "settle").Scan(&feeText, &gasText, &netText); err != nil {
		return domain.ZeroDecimal(), domain.ZeroDecimal(), domain.ZeroDecimal(), err
	}
	return decimalFromStringSafe(feeText), decimalFromStringSafe(gasText), decimalFromStringSafe(netText), nil
}

func (t *runtimeSQLTables) placeholder(i int) string {
	if t.dialect == "sqlite" {
		return "?"
	}
	return fmt.Sprintf("$%d", i)
}

func decimalFromStringSafe(value string) domain.Decimal {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return domain.ZeroDecimal()
	}
	return domain.MustDecimal(trimmed)
}

type decimalScanTarget struct {
	value *domain.Decimal
}

func stringScanner(target *domain.Decimal) *decimalScanTarget {
	return &decimalScanTarget{value: target}
}

func (d *decimalScanTarget) Scan(src any) error {
	if d == nil || d.value == nil {
		return nil
	}
	switch v := src.(type) {
	case nil:
		*d.value = domain.ZeroDecimal()
	case string:
		*d.value = decimalFromStringSafe(v)
	case []byte:
		*d.value = decimalFromStringSafe(string(v))
	default:
		*d.value = decimalFromStringSafe(fmt.Sprintf("%v", v))
	}
	return nil
}

func newLedgerEventID(prefix string, positionID string, blockTime int64) string {
	return fmt.Sprintf("%s:%s:%d", prefix, positionID, blockTime)
}

func nowUnixMilli() int64 {
	return time.Now().UnixMilli()
}

func loadPositionMetadata(raw string) map[string]any {
	payload := map[string]any{}
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || trimmed == "{}" {
		return payload
	}
	if err := json.Unmarshal([]byte(trimmed), &payload); err != nil {
		return map[string]any{}
	}
	return payload
}

func metadataString(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	value, ok := payload[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return strings.TrimSpace(fmt.Sprintf("%v", typed))
	}
}

func metadataDecimal(payload map[string]any, key string) domain.Decimal {
	return decimalFromStringSafe(metadataString(payload, key))
}
