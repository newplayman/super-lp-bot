package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
	"github.com/shopspring/decimal"
)

const (
	meteoraDLMMAPIBase = "https://dlmm.datapi.meteora.ag"
	orcaAPIBase        = "https://api.orca.so"
	raydiumAPIBase     = "https://api-v3.raydium.io"
)

func discoverNativeSolanaPools(ctx context.Context, protocolFilter string, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, string, error) {
	protocolFilter = strings.ToLower(strings.TrimSpace(protocolFilter))
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}

	var all []ports.PoolDiscovery
	var sources []string
	var errs []string
	fetch := func(protocol string, fn func(context.Context, domain.Decimal, int) ([]ports.PoolDiscovery, error)) {
		if protocolFilter != "" && protocolFilter != protocol {
			return
		}
		pools, err := fn(ctx, minTVLUSD, limit)
		if err != nil {
			errs = append(errs, protocol+": "+err.Error())
			return
		}
		all = append(all, pools...)
		sources = append(sources, protocol)
	}

	fetch("meteora-dlmm", fetchMeteoraDLMMPools)
	fetch("orca-whirlpool", fetchOrcaWhirlpoolPools)
	fetch("raydium-clmm", fetchRaydiumCLMMPools)

	if len(all) > 0 {
		return dedupePoolDiscovery(all), "native:" + strings.Join(sources, ","), nil
	}
	if len(errs) > 0 {
		return nil, "", fmt.Errorf(strings.Join(errs, "; "))
	}
	return nil, "", nil
}

func fetchMeteoraDLMMPools(ctx context.Context, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	endpoint := fmt.Sprintf("%s/pools?page=1&page_size=%d", meteoraDLMMAPIBase, limit)
	var payload struct {
		Data []struct {
			Address    string          `json:"address"`
			TVL        json.RawMessage `json:"tvl"`
			Current    json.RawMessage `json:"current_price"`
			Volume     map[string]any  `json:"volume"`
			PoolConfig struct {
				BaseFeePct json.RawMessage `json:"base_fee_pct"`
			} `json:"pool_config"`
			TokenX struct {
				Address string `json:"address"`
			} `json:"token_x"`
			TokenY struct {
				Address string `json:"address"`
			} `json:"token_y"`
		} `json:"data"`
	}
	if err := getJSON(ctx, endpoint, &payload); err != nil {
		return nil, err
	}
	out := make([]ports.PoolDiscovery, 0, len(payload.Data))
	for _, item := range payload.Data {
		tvl := decimalFromRaw(item.TVL)
		if tvl.LessThan(minTVLUSD) {
			continue
		}
		token0, _ := domain.ParseAddress(item.TokenX.Address)
		token1, _ := domain.ParseAddress(item.TokenY.Address)
		vol24h := decimalFromAny(item.Volume["24h"])
		feeBPS := uint(decimalFromRaw(item.PoolConfig.BaseFeePct).Mul(domain.MustDecimal("100")).Round(0).IntPart())
		out = append(out, ports.PoolDiscovery{
			ID:        item.Address,
			Chain:     domain.ChainSolana,
			Protocol:  "meteora-dlmm",
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    feeBPS,
			TVLUSD:    tvl,
			Vol24h:    vol24h,
			PriceUSD:  decimalFromRaw(item.Current),
			UpdatedAt: time.Now(),
		})
	}
	return out, nil
}

func fetchOrcaWhirlpoolPools(ctx context.Context, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	values := url.Values{}
	values.Set("size", fmt.Sprintf("%d", limit))
	values.Set("sortBy", "volume24h")
	values.Set("sortDirection", "desc")
	endpoint := orcaAPIBase + "/v2/solana/pools?" + values.Encode()
	var payload struct {
		Data []struct {
			Address    string          `json:"address"`
			FeeRate    json.RawMessage `json:"feeRate"`
			TokenMintA string          `json:"tokenMintA"`
			TokenMintB string          `json:"tokenMintB"`
			TVLUSDC    json.RawMessage `json:"tvlUsdc"`
			Price      json.RawMessage `json:"price"`
			Stats      map[string]struct {
				Volume json.RawMessage `json:"volume"`
			} `json:"stats"`
		} `json:"data"`
	}
	if err := getJSON(ctx, endpoint, &payload); err != nil {
		return nil, err
	}
	out := make([]ports.PoolDiscovery, 0, len(payload.Data))
	for _, item := range payload.Data {
		tvl := decimalFromRaw(item.TVLUSDC)
		if tvl.LessThan(minTVLUSD) {
			continue
		}
		token0, _ := domain.ParseAddress(item.TokenMintA)
		token1, _ := domain.ParseAddress(item.TokenMintB)
		feeBPS := uint(decimalFromRaw(item.FeeRate).Div(domain.MustDecimal("100")).Round(0).IntPart())
		out = append(out, ports.PoolDiscovery{
			ID:        item.Address,
			Chain:     domain.ChainSolana,
			Protocol:  "orca-whirlpool",
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    feeBPS,
			TVLUSD:    tvl,
			Vol24h:    decimalFromRaw(item.Stats["24h"].Volume),
			PriceUSD:  decimalFromRaw(item.Price),
			UpdatedAt: time.Now(),
		})
	}
	return out, nil
}

func fetchRaydiumCLMMPools(ctx context.Context, minTVLUSD domain.Decimal, limit int) ([]ports.PoolDiscovery, error) {
	values := url.Values{}
	values.Set("poolType", "concentrated")
	values.Set("poolSortField", "volume24h")
	values.Set("sortType", "desc")
	values.Set("pageSize", fmt.Sprintf("%d", limit))
	values.Set("page", "1")
	endpoint := raydiumAPIBase + "/pools/info/list?" + values.Encode()
	var payload struct {
		Data struct {
			Data []struct {
				ID      string          `json:"id"`
				FeeRate json.RawMessage `json:"feeRate"`
				TVL     json.RawMessage `json:"tvl"`
				Price   json.RawMessage `json:"price"`
				MintA   struct {
					Address string `json:"address"`
				} `json:"mintA"`
				MintB struct {
					Address string `json:"address"`
				} `json:"mintB"`
				Day struct {
					Volume json.RawMessage `json:"volume"`
				} `json:"day"`
			} `json:"data"`
		} `json:"data"`
	}
	if err := getJSON(ctx, endpoint, &payload); err != nil {
		return nil, err
	}
	out := make([]ports.PoolDiscovery, 0, len(payload.Data.Data))
	for _, item := range payload.Data.Data {
		tvl := decimalFromRaw(item.TVL)
		if tvl.LessThan(minTVLUSD) {
			continue
		}
		token0, _ := domain.ParseAddress(item.MintA.Address)
		token1, _ := domain.ParseAddress(item.MintB.Address)
		feeBPS := uint(decimalFromRaw(item.FeeRate).Mul(domain.MustDecimal("10000")).Round(0).IntPart())
		out = append(out, ports.PoolDiscovery{
			ID:        item.ID,
			Chain:     domain.ChainSolana,
			Protocol:  "raydium-clmm",
			Token0:    token0,
			Token1:    token1,
			FeeBPS:    feeBPS,
			TVLUSD:    tvl,
			Vol24h:    decimalFromRaw(item.Day.Volume),
			PriceUSD:  decimalFromRaw(item.Price),
			UpdatedAt: time.Now(),
		})
	}
	return out, nil
}

func getJSON(ctx context.Context, endpoint string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "lpbot-solana-tierc-discovery/1.0")
	client := &http.Client{Timeout: 20 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("GET %s: status=%d body=%s", endpoint, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if len(body) == 0 {
		return fmt.Errorf("GET %s: empty response", endpoint)
	}
	return json.Unmarshal(body, target)
}

func decimalFromRaw(raw json.RawMessage) domain.Decimal {
	if len(raw) == 0 || string(raw) == "null" {
		return domain.ZeroDecimal()
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return decimalFromString(s)
	}
	var f float64
	if err := json.Unmarshal(raw, &f); err == nil && !math.IsNaN(f) && !math.IsInf(f, 0) {
		return domain.NewDecimalFromFloat(f)
	}
	return domain.ZeroDecimal()
}

func decimalFromAny(value any) domain.Decimal {
	switch v := value.(type) {
	case nil:
		return domain.ZeroDecimal()
	case string:
		return decimalFromString(v)
	case float64:
		return domain.NewDecimalFromFloat(v)
	case json.Number:
		return decimalFromString(v.String())
	default:
		return domain.ZeroDecimal()
	}
}

func decimalFromString(raw string) domain.Decimal {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return domain.ZeroDecimal()
	}
	d, err := decimal.NewFromString(raw)
	if err != nil {
		return domain.ZeroDecimal()
	}
	return d
}

func dedupePoolDiscovery(pools []ports.PoolDiscovery) []ports.PoolDiscovery {
	seen := make(map[string]bool, len(pools))
	out := make([]ports.PoolDiscovery, 0, len(pools))
	for _, pool := range pools {
		key := pool.Protocol + ":" + pool.ID
		if seen[key] || strings.TrimSpace(pool.ID) == "" {
			continue
		}
		seen[key] = true
		out = append(out, pool)
	}
	return out
}
