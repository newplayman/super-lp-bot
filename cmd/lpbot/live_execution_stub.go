//go:build !live

package main

import "context"

func configureLiveExecution(_ context.Context, _ *App, _ *orderManagerAdapter) error {
	return nil
}
