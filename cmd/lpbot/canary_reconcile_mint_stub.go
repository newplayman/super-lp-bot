//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runCanaryMintReconcile(_ context.Context, _ *config.Config, _ string) error {
	return fmt.Errorf("canary mint reconcile requires a live build")
}
