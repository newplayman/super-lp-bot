// Package abi contains ABI definitions for Base chain contracts.
// These ABIs are used for encoding/decoding calldata.
package abi

import (
	"bytes"
	_ "embed" // Required for //go:embed directives

	"github.com/ethereum/go-ethereum/accounts/abi"
)

//go:embed npm_abi.json
var npmABIJSON string

// NPMABI is the ABI for NonfungiblePositionManager (UniV3 style).
var NPMABI abi.ABI

func init() {
	var err error
	NPMABI, err = abi.JSON(bytes.NewReader([]byte(npmABIJSON)))
	if err != nil {
		panic("failed to parse NPM ABI: " + err.Error())
	}
}

// NPMContractAddresses contains the NPM contract addresses by chain.
var NPMContractAddresses = map[string]string{
	"base": "0x03b18bC58B8e9f1b7D2F0F2E5d5F5b8e9f1b7D2F0F", // Placeholder - should be loaded from config
}

// GetNPMAddress returns the NPM contract address for a given chain.
func GetNPMAddress(chain string) string {
	if addr, ok := NPMContractAddresses[chain]; ok {
		return addr
	}
	return ""
}
