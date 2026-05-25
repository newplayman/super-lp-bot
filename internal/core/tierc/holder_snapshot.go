package tierc

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/lpbot/lpbot/internal/domain"
)

const DefaultHolderSnapshotPath = "configs/tierc_holder_overrides.json"

type HolderSnapshotEntry struct {
	Chain          string `json:"chain"`
	Token          string `json:"token"`
	Top10HolderPct string `json:"top10_holder_pct"`
	Source         string `json:"source,omitempty"`
	Note           string `json:"note,omitempty"`
}

type holderSnapshotFile struct {
	UpdatedAt string                `json:"updated_at,omitempty"`
	Entries   []HolderSnapshotEntry `json:"entries"`
}

type HolderSnapshotProvider struct {
	values map[string]domain.Decimal
}

func NewHolderSnapshotProviderFromFile(path string) (HolderSnapshotProvider, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return HolderSnapshotProvider{}, err
	}

	var payload holderSnapshotFile
	if err := json.Unmarshal(raw, &payload); err != nil {
		return HolderSnapshotProvider{}, fmt.Errorf("decode holder snapshot file: %w", err)
	}

	values := make(map[string]domain.Decimal, len(payload.Entries))
	for _, entry := range payload.Entries {
		chain := strings.ToLower(strings.TrimSpace(entry.Chain))
		token := strings.ToLower(strings.TrimSpace(entry.Token))
		if chain == "" || token == "" {
			continue
		}
		pct := strings.TrimSpace(entry.Top10HolderPct)
		if pct == "" {
			continue
		}
		values[chain+"|"+token] = domain.MustDecimal(pct)
	}
	return HolderSnapshotProvider{values: values}, nil
}

func (p HolderSnapshotProvider) Top10HolderPct(_ context.Context, chain domain.ChainID, token domain.Address) (domain.Decimal, error) {
	if len(p.values) == 0 {
		return domain.ZeroDecimal(), nil
	}
	key := strings.ToLower(string(chain)) + "|" + strings.ToLower(strings.TrimSpace(token.String()))
	if pct, ok := p.values[key]; ok {
		return pct, nil
	}
	return domain.ZeroDecimal(), nil
}

type ChainedHolderConcentrationProvider struct {
	Providers []HolderConcentrationProvider
}

func (p ChainedHolderConcentrationProvider) Top10HolderPct(ctx context.Context, chain domain.ChainID, token domain.Address) (domain.Decimal, error) {
	var lastErr error
	for _, provider := range p.Providers {
		if provider == nil {
			continue
		}
		pct, err := provider.Top10HolderPct(ctx, chain, token)
		if err != nil {
			lastErr = err
			continue
		}
		if pct.GreaterThan(domain.ZeroDecimal()) {
			return pct, nil
		}
	}
	if lastErr != nil {
		return domain.ZeroDecimal(), lastErr
	}
	return domain.ZeroDecimal(), nil
}
