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
	fmt.Printf("lpbot binary: %s (Phase 0 work-in-progress)\n", os.Args[0])
	fmt.Println("see ../docs/superpowers/plans/2026-05-19-lp-bot-phase-0.md")
	os.Exit(0)
}
