//go:build dryrun
// +build dryrun

package main

import (
	"fmt"
)

// init sets the build mode for dryrun builds.
func init() {
	BuildMode = "dryrun"
}

// validateMode performs dryrun-specific validation.
func validateMode() error {
	fmt.Println("=== DRYRUN MODE ===")
	fmt.Println("This is a dry-run simulation. No real transactions will be sent.")
	fmt.Println("Configure via: configs/config.dryrun.toml")
	return nil
}