//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaLPPrefundCanary(_ context.Context, _ *config.Config, _ string, _ string, _ int, _ uint64, _ uint64) error {
	return fmt.Errorf("solana lp prefund canary requires a live build")
}
