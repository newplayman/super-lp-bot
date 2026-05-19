package main

import (
	"fmt"
	"os"
)

const Version = "0.0.0-phase0"

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Println(Version)
		os.Exit(0)
	}
	fmt.Printf("lpbot-backtest: %s (Phase 0 stub — implementation in M0.13)\n", os.Args[0])
	os.Exit(0)
}
