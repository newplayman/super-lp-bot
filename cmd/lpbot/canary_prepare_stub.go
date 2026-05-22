//go:build !live

package main

import (
	"context"
	"fmt"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func runCanaryPrepare(_ context.Context, _ *config.Config) error {
	return fmt.Errorf("canary prepare requires a live build")
}
