//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runCanaryMint(_ context.Context, _ *config.Config) error {
	return fmt.Errorf("canary mint requires a live build")
}
