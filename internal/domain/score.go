package domain

// Score holds multi-dimensional scoring for a pool.
type Score struct {
	// Component scores (0–100)
	FeeAPRScore     float64 // 24h fee APR score
	TvlScore        float64 // TVL score
	VolScore        float64 // Volume score
	VolatilityScore float64 // Volatility (lower = more stable)
	SecurityScore   float64 // Rug/honeypot security score

	// Aggregated total (0–100)
	Total float64
}

// ComputeTotal calculates weighted aggregate score.
// Weights: FeeAPR=0.3, TVL=0.2, Vol=0.2, Volatility=0.1, Security=0.2
func (s Score) ComputeTotal() float64 {
	return s.FeeAPRScore*0.3 + s.TvlScore*0.2 + s.VolScore*0.2 +
		s.VolatilityScore*0.1 + s.SecurityScore*0.2
}

// AssignTier derives a Tier from the total score.
func (s Score) AssignTier() Tier {
	switch {
	case s.Total >= 75:
		return TierA
	case s.Total >= 50:
		return TierB
	default:
		return TierC
	}
}