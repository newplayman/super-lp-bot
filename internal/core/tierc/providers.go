package tierc

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

type HolderConcentrationProvider interface {
	Top10HolderPct(ctx context.Context, chain domain.ChainID, token domain.Address) (domain.Decimal, error)
}

type TraderConcentrationProvider interface {
	Concentration(ctx context.Context, chain domain.ChainID, poolID string) (map[string]string, error)
}

type NoopHolderConcentrationProvider struct{}

func (NoopHolderConcentrationProvider) Top10HolderPct(context.Context, domain.ChainID, domain.Address) (domain.Decimal, error) {
	return domain.ZeroDecimal(), nil
}

type NoopTraderConcentrationProvider struct{}

func (NoopTraderConcentrationProvider) Concentration(context.Context, domain.ChainID, string) (map[string]string, error) {
	return map[string]string{}, nil
}
