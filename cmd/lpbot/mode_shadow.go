//go:build shadow
// +build shadow

package main

import (
	"fmt"
)

// init sets the build mode for shadow builds.
func init() {
	BuildMode = "shadow"
}

// validateMode performs shadow-specific validation.
func validateMode() error {
	fmt.Println("=== SHADOW MODE ===")
	fmt.Println("Running in shadow mode: simulating transactions without real execution.")
	fmt.Println("Configure via: configs/config.shadow.toml")
	return nil
}