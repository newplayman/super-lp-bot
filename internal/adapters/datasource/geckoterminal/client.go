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
	Timestamp int64
	Open      string
	High      string
	Low       string
	Close     string
	Volume    string
}

// OHLCVListResponse represents the OHLCV API response from GeckoTerminal.
type OHLCVListResponse struct {
	Data struct {
		ID         string `json:"id"`
		Type       string `json:"type"`
		Attributes struct {
			OHLCVList [][]json.Number `json:"ohlcv_list"`
		} `json:"attributes"`
	} `json:"data"`
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
			M5  string `json:"m5"`
			H1  string `json:"h1"`
			H6  string `json:"h6"`
			H24 string `json:"h24"`
		} `json:"volume_usd"`
		Transactions struct {
			M5  TransactionWindow `json:"m5"`
			H1  TransactionWindow `json:"h1"`
			H6  TransactionWindow `json:"h6"`
			H24 TransactionWindow `json:"h24"`
		} `json:"transactions"`
		PriceChangePercentage struct {
			M5  string `json:"m5"`
			H1  string `json:"h1"`
			H6  string `json:"h6"`
			H24 string `json:"h24"`
		} `json:"price_change_percentage"`
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

type TransactionWindow struct {
	Buys    int64 `json:"buys"`
	Sells   int64 `json:"sells"`
	Buyers  int64 `json:"buyers"`
	Sellers int64 `json:"sellers"`
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
	pathTimeframe, aggregate := normalizeOHLCVTimeframe(timeframe)

	u, err := url.Parse(fmt.Sprintf("%s/networks/%s/pools/%s/ohlcv/%s", c.baseURL, network, poolAddress, pathTimeframe))
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("timestamp_start", fmt.Sprintf("%d", from))
	query.Set("timestamp_end", fmt.Sprintf("%d", to))
	query.Set("limit", fmt.Sprintf("%d", limit))
	if aggregate > 1 {
		query.Set("aggregate", fmt.Sprintf("%d", aggregate))
	}
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

	candles := make([]OHLCV, 0, len(result.Data.Attributes.OHLCVList))
	for _, tuple := range result.Data.Attributes.OHLCVList {
		if len(tuple) < 6 {
			continue
		}
		timestamp, err := tuple[0].Int64()
		if err != nil {
			continue
		}
		candles = append(candles, OHLCV{
			Timestamp: timestamp,
			Open:      tuple[1].String(),
			High:      tuple[2].String(),
			Low:       tuple[3].String(),
			Close:     tuple[4].String(),
			Volume:    tuple[5].String(),
		})
	}

	return candles, nil
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
	pageLimit := 20
	if limit < pageLimit {
		pageLimit = limit
	}
	maxPages := (limit + pageLimit - 1) / pageLimit
	if maxPages > 2 {
		maxPages = 2
	}

	result := make([]PoolInfo, 0, limit)
	for page := 1; page <= maxPages && len(result) < limit; page++ {
		pools, err := c.getPoolsByNetworkPage(ctx, network, page, pageLimit)
		if err != nil {
			if len(result) > 0 {
				return result, nil
			}
			return nil, err
		}
		if len(pools) == 0 {
			break
		}
		remaining := limit - len(result)
		if len(pools) > remaining {
			pools = pools[:remaining]
		}
		result = append(result, pools...)
		if len(pools) < pageLimit {
			break
		}
	}
	return result, nil
}

func (c *Client) getPoolsByNetworkPage(ctx context.Context, network string, page int, limit int) ([]PoolInfo, error) {
	u, err := url.Parse(fmt.Sprintf("%s/networks/%s/pools", c.baseURL, network))
	if err != nil {
		return nil, fmt.Errorf("parse URL: %w", err)
	}

	query := u.Query()
	query.Set("page", fmt.Sprintf("%d", page))
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

func normalizeOHLCVTimeframe(timeframe string) (string, int) {
	switch timeframe {
	case "5m":
		return "minute", 5
	case "1m", "minute":
		return "minute", 1
	case "1h", "hour":
		return "hour", 1
	case "1d", "day":
		return "day", 1
	case "second":
		return "second", 1
	default:
		return "minute", 1
	}
}
