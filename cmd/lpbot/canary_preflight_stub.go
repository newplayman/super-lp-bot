//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runCanaryPreflight(_ context.Context, _ *config.Config) error {
	return fmt.Errorf("canary preflight requires a live build")
}
