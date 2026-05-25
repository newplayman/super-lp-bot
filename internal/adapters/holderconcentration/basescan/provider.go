package basescan

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/shopspring/decimal"
)

const (
	defaultBaseScanURL    = "https://api.basescan.org/api"
	defaultEtherscanV2URL = "https://api.etherscan.io/v2/api"
	baseScanWebURL        = "https://basescan.org"
	baseChainID           = "8453"
)

var top10HolderPctPattern = regexp.MustCompile(`(?is)Top\s*10\s*holders:\s*<strong>\s*([0-9]+(?:\.[0-9]+)?)%\s*</strong>`)

type Provider struct {
	client    *http.Client
	baseURL   string
	apiKey    string
	useChainID bool
}

type holderListResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
	Result  []struct {
		Address  string `json:"TokenHolderAddress"`
		Quantity string `json:"TokenHolderQuantity"`
	} `json:"result"`
}

type totalSupplyResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
	Result  string `json:"result"`
}

func NewProviderFromEnv() (*Provider, bool) {
	if apiKey := strings.TrimSpace(os.Getenv("BASESCAN_API_KEY")); apiKey != "" {
		baseURL := strings.TrimSpace(os.Getenv("BASESCAN_API_URL"))
		if baseURL == "" {
			baseURL = defaultBaseScanURL
		}
		return &Provider{
			client:  &http.Client{Timeout: 20 * time.Second},
			baseURL: baseURL,
			apiKey:  apiKey,
		}, true
	}

	if apiKey := strings.TrimSpace(os.Getenv("ETHERSCAN_API_KEY")); apiKey != "" {
		return &Provider{
			client:     &http.Client{Timeout: 20 * time.Second},
			baseURL:    defaultEtherscanV2URL,
			apiKey:     apiKey,
			useChainID: true,
		}, true
	}

	return nil, false
}

func (p *Provider) Top10HolderPct(ctx context.Context, chain domain.ChainID, token domain.Address) (domain.Decimal, error) {
	if p == nil || strings.TrimSpace(p.apiKey) == "" {
		return domain.ZeroDecimal(), nil
	}
	if chain != domain.ChainBase {
		return domain.ZeroDecimal(), nil
	}
	tokenAddress := strings.TrimSpace(token.String())
	if tokenAddress == "" || token.IsZero() {
		return domain.ZeroDecimal(), nil
	}

	totalSupply, err := p.fetchTotalSupply(ctx, tokenAddress)
	topHolders, holderErr := p.fetchTopHolders(ctx, tokenAddress)
	if err == nil && !totalSupply.IsZero() && holderErr == nil && len(topHolders) > 0 {
		sum := domain.ZeroDecimal()
		for _, quantity := range topHolders {
			sum = sum.Add(quantity)
		}
		return sum.Div(totalSupply).Mul(domain.MustDecimal("100")), nil
	}

	fallbackPct, fallbackErr := p.fetchTop10HolderPctFromHTML(ctx, tokenAddress)
	if fallbackErr == nil {
		return fallbackPct, nil
	}

	if err != nil && holderErr != nil {
		return domain.ZeroDecimal(), fmt.Errorf("api path failed (%v; %v); html fallback failed: %w", err, holderErr, fallbackErr)
	}
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("total supply api failed: %v; html fallback failed: %w", err, fallbackErr)
	}
	if holderErr != nil {
		return domain.ZeroDecimal(), fmt.Errorf("holder list api failed: %v; html fallback failed: %w", holderErr, fallbackErr)
	}
	return domain.ZeroDecimal(), fmt.Errorf("api path returned empty holder data; html fallback failed: %w", fallbackErr)
}

func (p *Provider) fetchTopHolders(ctx context.Context, tokenAddress string) ([]domain.Decimal, error) {
	u, err := url.Parse(p.baseURL)
	if err != nil {
		return nil, fmt.Errorf("parse holder list url: %w", err)
	}
	query := u.Query()
	if p.useChainID {
		query.Set("chainid", baseChainID)
	}
	query.Set("module", "token")
	query.Set("action", "tokenholderlist")
	query.Set("contractaddress", tokenAddress)
	query.Set("page", "1")
	query.Set("offset", "10")
	query.Set("apikey", p.apiKey)
	u.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create holder list request: %w", err)
	}
	resp, err := p.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute holder list request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("holder list unexpected status: %d", resp.StatusCode)
	}

	var payload holderListResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode holder list response: %w", err)
	}
	if payload.Status != "1" {
		return nil, fmt.Errorf("holder list api status=%s message=%s", payload.Status, payload.Message)
	}

	out := make([]domain.Decimal, 0, len(payload.Result))
	for _, holder := range payload.Result {
		qty, err := decimal.NewFromString(holder.Quantity)
		if err != nil {
			continue
		}
		out = append(out, qty)
	}
	return out, nil
}

func (p *Provider) fetchTotalSupply(ctx context.Context, tokenAddress string) (domain.Decimal, error) {
	u, err := url.Parse(p.baseURL)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("parse total supply url: %w", err)
	}
	query := u.Query()
	if p.useChainID {
		query.Set("chainid", baseChainID)
	}
	query.Set("module", "stats")
	query.Set("action", "tokensupply")
	query.Set("contractaddress", tokenAddress)
	query.Set("apikey", p.apiKey)
	u.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("create total supply request: %w", err)
	}
	resp, err := p.client.Do(req)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("execute total supply request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return domain.ZeroDecimal(), fmt.Errorf("total supply unexpected status: %d", resp.StatusCode)
	}

	var payload totalSupplyResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("decode total supply response: %w", err)
	}
	if payload.Status != "1" {
		return domain.ZeroDecimal(), fmt.Errorf("total supply api status=%s message=%s", payload.Status, payload.Message)
	}

	totalSupply, err := decimal.NewFromString(payload.Result)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("parse total supply: %w", err)
	}
	return totalSupply, nil
}

func (p *Provider) fetchTop10HolderPctFromHTML(ctx context.Context, tokenAddress string) (domain.Decimal, error) {
	u, err := url.Parse(baseScanWebURL + "/token/generic-tokenholders2")
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("parse holder html url: %w", err)
	}
	query := u.Query()
	query.Set("a", tokenAddress)
	u.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("create holder html request: %w", err)
	}
	resp, err := p.client.Do(req)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("execute holder html request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return domain.ZeroDecimal(), fmt.Errorf("holder html unexpected status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("read holder html response: %w", err)
	}
	match := top10HolderPctPattern.FindSubmatch(body)
	if len(match) != 2 {
		return domain.ZeroDecimal(), fmt.Errorf("top 10 holder percentage not found in holder html")
	}

	pct, err := decimal.NewFromString(string(match[1]))
	if err != nil {
		return domain.ZeroDecimal(), fmt.Errorf("parse holder html top10 percentage: %w", err)
	}
	return pct, nil
}
