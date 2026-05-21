// Package geckoterminal provides a GeckoTerminal datasource adapter.
//
// This adapter fetches pool discovery and metadata from GeckoTerminal API.
// It also implements HistoricalDatasource for historical OHLCV price data.
package geckoterminal

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// RateLimitError indicates GeckoTerminal returned HTTP 429.
type RateLimitError struct {
	StatusCode int
	RetryAfter time.Duration
}

func (e *RateLimitError) Error() string {
	return fmt.Sprintf("rate limited: status %d", e.StatusCode)
}

// Client handles HTTP communication with GeckoTerminal API.
type Client struct {
	client  *http.Client
	baseURL string
}

// NewClient creates a new GeckoTerminal API client.
func NewClient() *Client {
	return &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: "https://api.geckoterminal.com/api/v2",
	}
}

func NewClientWithHTTP(client *http.Client, baseURL string) *Client {
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	if baseURL == "" {
		baseURL = "https://api.geckoterminal.com/api/v2"
	}
	return &Client{client: client, baseURL: baseURL}
}

// OHLCV represents a single OHLCV candle from GeckoTerminal.
type OHLCV struct {
	Attributes struct {
		OHLCVOpen   string `json:"ohlcv_open"`
		OHLCVHigh   string `json:"ohlcv_high"`
		OHLCVLow    string `json:"ohlcv_low"`
		OHLCVClose  string `json:"ohlcv_close"`
		OHLCVVolume string `json:"ohlcv_volume"`
		Timestamp   string `json:"timestamp"`
		BlockTime   string `json:"block_time"`
		Transaction string `json:"transaction"`
		TxHash      string `json:"tx_hash"`
		TxFrom      string `json:"tx_from"`
		TxTo        string `json:"tx_to"`
		TxType      string `json:"tx_type"`
	} `json:"relationships"`
}

// OHLCVListResponse represents the OHLCV API response from GeckoTerminal.
type OHLCVListResponse struct {
	Data  []OHLCV `json:"data"`
	Links struct {
		Next string `json:"next"`
	} `json:"links"`
}

// PoolResponse represents a pool info response from GeckoTerminal.
type PoolResponse struct {
	Data PoolInfo `json:"data"`
}

// PoolInfo represents pool information from GeckoTerminal.
type PoolInfo struct {
	ID         string `json:"id"`
	Type       string `json:"type"`
	Attributes struct {
		Address           string `json:"address"`
		Name              string `json:"name"`
		BaseVolume        string `json:"base_volume"`
		QuoteVolume       string `json:"quote_volume"`
		BaseLiquidityUSD  string `json:"base_liquidity_usd"`
		QuoteLiquidityUSD string `json:"quote_liquidity_usd"`
		LiquidityUSD      string `json:"liquidity_usd"`
		ReserveInUSD      string `json:"reserve_in_usd"`
		PriceUSD          string `json:"price_usd"`
		PriceNative       string `json:"price_native"`
		TxCount           string `json:"tx_count"`
		PoolCreated       string `json:"pool_created"`
		Token0            Token  `json:"token0"`
		Token1            Token  `json:"token1"`
		VolumeUSD         struct {
			H24 string `json:"h24"`
		} `json:"volume_usd"`
	} `json:"attributes"`
	Relationships struct {
		BaseToken struct {
			Data struct {
				ID string `json:"id"`
			} `json:"data"`
		} `json:"base_token"`
		QuoteToken struct {
			Data struct {
				ID string `json:"id"`
			} `json:"data"`
		} `json:"quote_token"`
		Dex struct {
			Data struct {
				ID string `json:"id"`
			} `json:"data"`
		} `json:"dex"`
	} `json:"relationships"`
}

// Token represents token info from GeckoTerminal.
type Token struct {
	Address  string `json:"address"`
	Symbol   string `json:"symbol"`
	Name     string `json:"name"`
	Decimals string `json:"decimals"`
}

// GetOHLCV fetches OHLCV data for a pool.
func (c *Client) GetOHLCV(ctx context.Context, network, poolAddress, timeframe string, from, to int64, limit int) ([]OHLCV, error) {
	if limit <= 0 {
		limit = 1000
	}

	u, err := url.Parse(fmt.Sprintf("%s/networks/%s/pools/%s/ohlcv/%s", c.baseURL, network, poolAddress, timeframe))
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("timestamp_start", fmt.Sprintf("%d", from))
	query.Set("timestamp_end", fmt.Sprintf("%d", to))
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

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, rateLimitFromResponse(resp)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result OHLCVListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return result.Data, nil
}

// GetPoolInfo fetches pool info for a specific pool.
func (c *Client) GetPoolInfo(ctx context.Context, network, poolAddress string) (*PoolInfo, error) {
	u, err := url.Parse(fmt.Sprintf("%s/networks/%s/pools/%s", c.baseURL, network, poolAddress))
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

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, rateLimitFromResponse(resp)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result PoolResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return &result.Data, nil
}

// HealthCheck verifies the GeckoTerminal API is accessible.
func (c *Client) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL, nil)
	if err != nil {
		return err
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return rateLimitFromResponse(resp)
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed: status %d", resp.StatusCode)
	}

	return nil
}

// PoolListResponse represents the pool list response from GeckoTerminal.
type PoolListResponse struct {
	Data  []PoolInfo `json:"data"`
	Links struct {
		Next string `json:"next"`
	} `json:"links"`
}

// GetPoolsByNetwork fetches top pools for a network.
func (c *Client) GetPoolsByNetwork(ctx context.Context, network string, limit int) ([]PoolInfo, error) {
	if limit <= 0 {
		limit = 50
	}

	u, err := url.Parse(fmt.Sprintf("%s/networks/%s/pools", c.baseURL, network))
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("page", "1")
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

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, rateLimitFromResponse(resp)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result PoolListResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return result.Data, nil
}

func rateLimitFromResponse(resp *http.Response) error {
	retryAfter := 2 * time.Minute
	if value := resp.Header.Get("Retry-After"); value != "" {
		if seconds, err := strconv.Atoi(value); err == nil && seconds > 0 {
			retryAfter = time.Duration(seconds) * time.Second
		}
	}
	return &RateLimitError{StatusCode: resp.StatusCode, RetryAfter: retryAfter}
}
