package domain

import "fmt"

type ChainID string

const (
	ChainBase   ChainID = "base"
	ChainSolana ChainID = "solana"
)

func (c ChainID) String() string { return string(c) }

func ParseChainID(s string) (ChainID, error) {
	switch s {
	case "base":
		return ChainBase, nil
	case "solana":
		return ChainSolana, nil
	default:
		return "", fmt.Errorf("unknown chain: %q (Phase 1–3 only supports base, solana)", s)
	}
}

type BlockRef struct {
	Chain    ChainID
	Number   uint64
	Hash     string
	TimeUnix int64
}

func (b BlockRef) Equal(o BlockRef) bool {
	return b.Chain == o.Chain && b.Number == o.Number && b.Hash == o.Hash
}