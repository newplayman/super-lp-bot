package main

import (
	"testing"

	solanago "github.com/gagliardetto/solana-go"
)

func TestPancakeSolanaPoolRewardInfoLayoutMatchesFrontendSDK(t *testing.T) {
	data := make([]byte, 1544)
	mint := solanago.MustPublicKeyFromBase58("4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL")
	vault := solanago.MustPublicKeyFromBase58("DT9xPUBTdNoizh2RNvPTN6KXqoyqGFfSWsEArgCS7ryB")

	const rewardInfosOffset = 397
	const rewardMintOffset = 57
	const rewardVaultOffset = 89
	data[rewardInfosOffset] = 2
	copy(data[rewardInfosOffset+rewardMintOffset:rewardInfosOffset+rewardMintOffset+32], mint.Bytes())
	copy(data[rewardInfosOffset+rewardVaultOffset:rewardInfosOffset+rewardVaultOffset+32], vault.Bytes())

	rewards := decodePancakeSolanaRewardInfos(data)
	if len(rewards) != 1 {
		t.Fatalf("decoded rewards len = %d, want 1", len(rewards))
	}
	if rewards[0].Index != 0 {
		t.Fatalf("decoded reward index = %d, want 0", rewards[0].Index)
	}
	if !rewards[0].TokenMint.Equals(mint) {
		t.Fatalf("decoded reward mint = %s, want %s", rewards[0].TokenMint, mint)
	}
	if !rewards[0].TokenVault.Equals(vault) {
		t.Fatalf("decoded reward vault = %s, want %s", rewards[0].TokenVault, vault)
	}
}

func TestPancakeSolanaClosePositionDiscriminatorMatchesFrontendSDK(t *testing.T) {
	want := []byte{123, 134, 81, 0, 49, 68, 98, 98}
	if len(pancakeClosePositionDiscriminator) != len(want) {
		t.Fatalf("close discriminator len = %d, want %d", len(pancakeClosePositionDiscriminator), len(want))
	}
	for i := range want {
		if pancakeClosePositionDiscriminator[i] != want[i] {
			t.Fatalf("close discriminator[%d] = %d, want %d", i, pancakeClosePositionDiscriminator[i], want[i])
		}
	}
}
