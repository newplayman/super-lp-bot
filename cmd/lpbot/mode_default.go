//go:build !dryrun && !shadow && !live

package main

import (
	"fmt"
	"os"
)

func init() {
	BuildMode = "dev"
}

func validateMode() error {
	fmt.Fprintln(os.Stderr, "ERROR: lpbot must be built with a mode tag (-tags=dryrun|shadow|live)")
	fmt.Fprintln(os.Stderr, "For dryrun mode: go build -tags=dryrun -o lpbot-dryrun")
	fmt.Fprintln(os.Stderr, "For shadow mode: go build -tags=shadow -o lpbot-shadow")
	fmt.Fprintln(os.Stderr, "For live mode:   go build -tags=live -o lpbot-live")
	os.Exit(1)
	return nil
}