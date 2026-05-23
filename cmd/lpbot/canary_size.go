//go:build live

package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

const canarySizeEnv = "LPBOT_CANARY_SIZE_USD"

func selectCanaryAmountUSD(cfg *config.Config) (domain.Decimal, error) {
	if cfg == nil {
		return domain.ZeroDecimal(), fmt.Errorf("config is nil")
	}

	configuredMax := domain.NewDecimalFromFloat(cfg.Live.MaxOrderUSD)
	hardMax := domain.NewDecimalFromFloat(canaryMaxOrderUSD)
	if configuredMax.LessThanOrEqual(domain.ZeroDecimal()) {
		return domain.ZeroDecimal(), fmt.Errorf("invalid canary max_order_usd: %s", configuredMax.String())
	}
	if configuredMax.GreaterThan(hardMax) {
		return domain.ZeroDecimal(), fmt.Errorf("invalid canary max_order_usd: %s exceeds hard cap %s", configuredMax.String(), hardMax.String())
	}

	raw := strings.TrimSpace(os.Getenv(canarySizeEnv))
	if raw == "" {
		return configuredMax, nil
	}

	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("invalid %s=%q: %w", canarySizeEnv, raw, err)
	}
	if value != 5 && value != 10 && value != 20 {
		return domain.ZeroDecimal(), fmt.Errorf("invalid %s=%q: allowed values are 5, 10, 20", canarySizeEnv, raw)
	}

	amount := domain.NewDecimalFromFloat(value)
	if amount.GreaterThan(configuredMax) {
		return domain.ZeroDecimal(), fmt.Errorf("%s=%s exceeds live.max_order_usd %s", canarySizeEnv, amount.String(), configuredMax.String())
	}
	return amount, nil
}
