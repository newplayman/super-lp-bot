//go:build live
// +build live

package main

import (
	"fmt"
	"os"
)

// init sets the build mode for live builds.
func init() {
	BuildMode = "live"
}

// validateMode performs live-specific validation.
func validateMode() error {
	fmt.Println("=== LIVE MODE ===")
	fmt.Println("WARNING: Real transactions will be sent to the blockchain!")
	fmt.Println("Configure via: configs/config.live.toml")
	if os.Getenv("LPBOT_CONFIRM_LIVE") != "YES" {
		return fmt.Errorf("live mode requires LPBOT_CONFIRM_LIVE=YES")
	}
	return nil
}
