//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaLPCloseCanary(ctx context.Context, cfg *config.Config, maxPriorityLamports uint64) error {
	return fmt.Errorf("solana lp close canary requires a live build")
}
