//go:build !live

package main

import (
	"context"

	"github.com/lpbot/lpbot/internal/ports"
)

func (app *App) shouldRunBaseTxConfirmer() bool {
	return false
}

func (app *App) runBaseTxConfirmerLoop(context.Context) {}

func attachOpenTxHashToPosition(context.Context, ports.PositionRepo, string, string) error {
	return nil
}
