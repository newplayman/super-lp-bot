package domain_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestTokenAmount_InUSD(t *testing.T) {
	ta := domain.TokenAmount{
		Token:  domain.Token{Symbol: "USDC", Decimals: 6},
		Amount: domain.MustDecimal("1000000"), // 1 USDC (6 decimals)
	}
	price := domain.MustDecimal("1.0")
	require.Equal(t, "1", ta.InUSD(price).String())
}

func TestTokenAmount_Display(t *testing.T) {
	ta := domain.TokenAmount{
		Token:  domain.Token{Symbol: "USDC", Decimals: 6},
		Amount: domain.MustDecimal("1000000"),
	}
	require.Equal(t, "1", ta.Display())
}