package domain

import "fmt"

// Pool holds pool metadata (immutable fields + latest mutable state snapshot).
type Pool struct {
	ID        string  // on-chain pool address
	Chain     ChainID // chain identifier
	Protocol  string  // e.g. "uniswap_v3", "whirlpool"
	Token0    Address // first token in the pair
	Token1    Address // second token in the pair
	FeeBPS    uint    // fee in basis points (e.g. 30 = 0.3%)
	Tier_     Tier    // assigned tier
	Liquidity Decimal // current liquidity amount
	Tick      int     // current tick
	TVLUSD    Decimal // total value locked in USD
	Vol24h    Decimal // 24h swap volume in USD
	FeeAPR24h Decimal // 24h fee APR
	UpdatedAt int64   // unix timestamp
}

// Key returns a unique key for the pool: "{chain}:{protocol}:{id}"
func (p Pool) Key() string {
	return fmt.Sprintf("%s:%s:%s", p.Chain, p.Protocol, p.ID)
}

// IsActive returns true if the pool has TVL > 0
func (p Pool) IsActive() bool {
	return p.TVLUSD.GreaterThan(Decimal{})
}

// String returns a human-readable string representation of the pool
func (p Pool) String() string {
	return fmt.Sprintf("Pool{ID:%s Chain:%s Protocol:%s Tier:%s TVLUSD:%s}",
		p.ID, p.Chain, p.Protocol, p.Tier_, p.TVLUSD)
}