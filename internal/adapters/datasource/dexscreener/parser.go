package dexscreener

import (
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

// Parser handles parsing of DexScreener API responses into domain types.
type Parser struct{}

// NewParser creates a new DexScreener response parser.
func NewParser() *Parser {
	return &Parser{}
}

// ParseSwaps converts DexScreener swap data into ports.Swap events.
func (p *Parser) ParseSwaps(swaps []SwapData, chain domain.ChainID) ([]ports.Swap, error) {
	result := make([]ports.Swap, 0, len(swaps))

	for _, swap := range swaps {
		parsed, err := parseSwapData(swap, chain)
		if err != nil {
			continue
		}
		result = append(result, parsed)
	}

	return result, nil
}

// ParsePoolToPoolDiscovery converts a PoolInfo to ports.PoolDiscovery.
func (p *Parser) ParsePoolToPoolDiscovery(info *PoolInfo, chain domain.ChainID) *ports.PoolDiscovery {
	if info == nil {
		return nil
	}

	tvlUSD, _ := decimal.NewFromString(info.Liquidity.USD)
	vol24h, _ := decimal.NewFromString(info.Volume.H24)

	return &ports.PoolDiscovery{
		ID:        info.PoolAddress,
		Chain:     chain,
		Protocol:  info.Protocol,
		Token0:    domain.MustParseAddress(info.Token0.Address),
		Token1:    domain.MustParseAddress(info.Token1.Address),
		FeeBPS:    0,
		TVLUSD:    domain.Decimal(tvlUSD),
		Vol24h:    domain.Decimal(vol24h),
		UpdatedAt: time.Unix(info.CreatedAt, 0),
	}
}