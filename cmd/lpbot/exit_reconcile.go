package main

import (
	"context"
	"database/sql"
	"fmt"

	dexdomain "github.com/lpbot/lpbot/internal/domain"
)

type pendingShadowExitAction struct {
	PositionID string
	PoolID     string
	Chain      string
	TxHash     string
}

func (app *App) reconcileBuiltShadowExits(ctx context.Context, db *sql.DB) error {
	rows, err := db.QueryContext(ctx, `
		SELECT sea.position_id, sea.pool_id, sea.chain, sea.tx_hash
		FROM shadow_exit_actions sea
		JOIN positions p ON p.id = sea.position_id
		WHERE sea.action = 'shadow_close'
		  AND sea.tx_status = 'built'
		  AND p.status <> 'closed'
		ORDER BY sea.decision_time ASC, sea.id ASC
		LIMIT 50
	`)
	if err != nil {
		return fmt.Errorf("query pending shadow exits: %w", err)
	}
	defer rows.Close()

	pending := make([]pendingShadowExitAction, 0)
	for rows.Next() {
		var item pendingShadowExitAction
		if err := rows.Scan(&item.PositionID, &item.PoolID, &item.Chain, &item.TxHash); err != nil {
			return fmt.Errorf("scan pending shadow exit: %w", err)
		}
		pending = append(pending, item)
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate pending shadow exits: %w", err)
	}
	if len(pending) == 0 {
		return nil
	}

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin shadow exit reconciliation tx: %w", err)
	}
	defer tx.Rollback()

	for _, item := range pending {
		exitTx := dexdomain.SignedTx{
			UnsignedTx: dexdomain.UnsignedTx{
				ID:       item.TxHash,
				Chain:    dexdomain.ChainID(item.Chain),
				From:     zeroEVMAddress(),
				To:       parseAddressOrZero(item.PoolID),
				Value:    dexdomain.ZeroDecimal(),
				Deadline: 0,
				MinOut:   dexdomain.ZeroDecimal(),
			},
			Hash:   item.TxHash,
			Status: dexdomain.TxConfirmed,
		}
		if err := app.store.TxRepo().UpsertTx(ctx, exitTx); err != nil {
			return fmt.Errorf("reconcile tx %s: %w", item.TxHash, err)
		}
		if _, err := tx.ExecContext(ctx, `
			UPDATE shadow_exit_actions
			SET tx_status = $1
			WHERE position_id = $2
			  AND tx_hash = $3
		`, string(dexdomain.TxConfirmed), item.PositionID, item.TxHash); err != nil {
			return fmt.Errorf("update shadow exit action %s: %w", item.TxHash, err)
		}
		if err := app.store.PositionRepo().UpdateStatus(ctx, item.PositionID, dexdomain.StatusClosed); err != nil {
			return fmt.Errorf("close reconciled shadow position %s: %w", item.PositionID, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit shadow exit reconciliation tx: %w", err)
	}
	return nil
}
