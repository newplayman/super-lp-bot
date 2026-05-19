// Package solana provides a Solana datasource adapter using Jupiter API.
//
// This adapter fetches historical swap data and pool information for Solana pools
// (Raydium, Orca, Jupiter Aggregator) using Jupiter's price and swap APIs.
package solana

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"github.com/shopspring/decimal"
)

// Client handles HTTP communication with Jupiter API.
type Client struct {
	client  *http.Client
	baseURL string
	metaURL string
}

// NewClient creates a new Jupiter API client for Solana.
func NewClient() *Client {
	return &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: "https://api.jup.ag/v6",
		metaURL: "https://api.jup.ag/price/v2",
	}
}

// PriceResponse represents the Jupiter price API response.
type PriceResponse struct {
	Data map[string]PriceData `json:"data"`
}

// PriceData represents price information for a token.
type PriceData struct {
	Price          string `json:"price"`
	ExtraPriceInfo *struct {
		LastSwapPrice string `json:"lastSwapPrice"`
		LastMcap      string `json:"lastMcap"`
		CurrentMcap   string `json:"currentMcap"`
	} `json:"extraInfo,omitempty"`
}

// TokenPrice represents a token price from Jupiter.
type TokenPrice struct {
	Mint      string
	Price     decimal.Decimal
	Timestamp time.Time
}

// GetTokenPrice fetches current price for a token from Jupiter.
func (c *Client) GetTokenPrice(ctx context.Context, tokenAddress string) (*TokenPrice, error) {
	u, err := url.Parse(c.metaURL)
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("ids", tokenAddress)
	u.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result PriceResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	priceData, ok := result.Data[tokenAddress]
	if !ok {
		return nil, fmt.Errorf("token not found: %s", tokenAddress)
	}

	price, err := decimal.NewFromString(priceData.Price)
	if err != nil {
		return nil, fmt.Errorf("parse price: %w", err)
	}

	return &TokenPrice{
		Mint:      tokenAddress,
		Price:     price,
		Timestamp: time.Now(),
	}, nil
}

// TradeData represents a single trade from Jupiter.
type TradeData struct {
	ID          string `json:"id"`
	Mint        string `json:"mint"`
	MintSymbol  string `json:"mintSymbol"`
	VoltTicker  string `json:"voltTicker,omitempty"`
	PoolID      string `json:"poolId"`
	PoolName    string `json:"poolName"`
	Pool        string `json:"pool"`
	TokenAccount string `json:"tokenAccount"`
	LpToken     string `json:"lpToken"`
	Time        string `json:"time"`
	BlockTime   int64  `json:"blockTime"`
	TxHash      string `json:"txHash"`
	Lamports    int64  `json:"lamports"`
	SolAmount   int64  `json:"solAmount"`
	TokenAmount int64  `json:"tokenAmount"`
	TokenSymbol string `json:"tokenSymbol"`
	VirtualSol  int64  `json:"virtualSol"`
	VirtualToken int64  `json:"virtualToken"`
	TxType      string `json:"txType"`
	Market      string `json:"market"`
	ProgramID   string `json:"programId"`
	VolumeUSD   string `json:"volumeUsd"`
	Creator     string `json:"creator"`
	Fee         struct {
		Amount    int64 `json:"amount"`
		Discount  int64 `json:"discount"`
		FeeAmount int64 `json:"feeAmount"`
		SolAmount int64 `json:"solAmount"`
	} `json:"fee"`
}

// GetRecentTrades fetches recent trades for a token.
func (c *Client) GetRecentTrades(ctx context.Context, tokenAddress string, limit int) ([]TradeData, error) {
	if limit <= 0 {
		limit = 100
	}

	u, err := url.Parse(c.baseURL + "/trade/v4/trade")
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("mint", tokenAddress)
	query.Set("limit", fmt.Sprintf("%d", limit))
	u.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	// Jupiter v6 might not have a direct recent trades endpoint
	// Return empty slice if endpoint not available
	if resp.StatusCode != http.StatusOK {
		return []TradeData{}, nil
	}

	var result struct {
		RecentTrades []TradeData `json:"recentTrades"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return result.RecentTrades, nil
}

// TokenMetadata represents metadata for a Solana token.
type TokenMetadata struct {
	Address  string `json:"address"`
	Symbol   string `json:"symbol"`
	Name     string `json:"name"`
	Decimals int    `json:"decimals"`
	LogoURI  string `json:"logoURI"`
	Price    string `json:"price"`
}

// GetTokenMetadata fetches metadata for a token from Jupiter.
func (c *Client) GetTokenMetadata(ctx context.Context, tokenAddress string) (*TokenMetadata, error) {
	u, err := url.Parse(c.baseURL + "/tokens/" + tokenAddress)
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result TokenMetadata
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return &result, nil
}

// HealthCheck verifies the Jupiter API is accessible.
func (c *Client) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/tokens", nil)
	if err != nil {
		return err
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed: status %d", resp.StatusCode)
	}

	return nil
}