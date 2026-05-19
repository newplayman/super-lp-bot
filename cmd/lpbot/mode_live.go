//go:build live
// +build live

package main

import (
	"fmt"
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
	fmt.Println("Press Ctrl+C to abort within 10 seconds...")
	return nil
}