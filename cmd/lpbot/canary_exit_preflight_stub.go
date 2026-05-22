//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runCanaryExitPreflight(_ context.Context, _ *config.Config, _ string) error {
	return fmt.Errorf("canary exit preflight requires a live build")
}

func runCanaryExit(_ context.Context, _ *config.Config, _ string) error {
	return fmt.Errorf("canary exit requires a live build")
}
