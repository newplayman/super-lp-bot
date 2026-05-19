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
	fmt.Printf("lpbot-recon: %s (Phase 3 stub)\n", os.Args[0])
	os.Exit(0)
}
