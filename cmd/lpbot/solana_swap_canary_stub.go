//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaSwapCanary(_ context.Context, _ *config.Config, _ string, _ string, _ string, _ string, _ int, _ uint64) error {
	return fmt.Errorf("solana swap canary requires a live build")
}
