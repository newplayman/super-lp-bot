package dexscreener

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/shopspring/decimal"
)

// Client handles HTTP communication with DexScreener API.
type Client struct {
	client  *http.Client
	baseURL string
}

// NewClient creates a new DexScreener API client.
func NewClient() *Client {
	return &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: "https://api.dexscreener.com",
	}
}

// PoolToken represents a token in a DexScreener pool response.
type PoolToken struct {
	Address  string `json:"address"`
	Symbol   string `json:"symbol"`
	Name     string `json:"name"`
	Decimals int    `json:"decimals"`
	LogoURI  string `json:"logoURI,omitempty"`
	PriceUSD string `json:"priceUsd,omitempty"`
}

// PoolInfo represents pool information from DexScreener.
type PoolInfo struct {
	PoolID      string      `json:"pairAddress"`
	PoolAddress string      `json:"pairAddress"`
	ChainID     string      `json:"chainId"`
	DEX         string      `json:"dexId"`
	Protocol    string      `json:"protocolType"`
	Factory     string      `json:"factoryAddress,omitempty"`
	Token0      PoolToken   `json:"baseToken"`
	Token1      PoolToken   `json:"quoteToken"`
	Liquidity   Liquidity   `json:"liquidity"`
	PriceUSD    string      `json:"priceUsd"`
	PriceNative string      `json:"priceNative"`
	Txns        Txns        `json:"txns"`
	Volume      Volume      `json:"volume"`
	PriceChange PriceChange `json:"priceChange"`
	CreatedAt   int64       `json:"poolCreatedAtTimestamp"`
}

// Liquidity represents liquidity data from DexScreener.
type Liquidity struct {
	USD   json.Number `json:"usd"`
	Base  json.Number `json:"base"`
	Quote json.Number `json:"quote"`
}

// Txns represents transaction counts from DexScreener.
type Txns struct {
	M5  TxCount `json:"m5"`
	H1  TxCount `json:"h1"`
	H24 TxCount `json:"h24"`
}

// TxCount represents transaction counts for a time period.
type TxCount struct {
	Buys  int `json:"buys"`
	Sells int `json:"sells"`
}

// Volume represents volume data from DexScreener.
type Volume struct {
	M5  json.Number `json:"m5"`
	H1  json.Number `json:"h1"`
	H24 json.Number `json:"h24"`
	H6  json.Number `json:"h6"`
	H12 json.Number `json:"h12"`
}

// PriceChange represents price change data from DexScreener.
type PriceChange struct {
	M5  json.Number `json:"m5"`
	H1  json.Number `json:"h1"`
	H24 json.Number `json:"h24"`
	H6  json.Number `json:"h6"`
	H12 json.Number `json:"h12"`
}

// SearchResponse represents the DexScreener search API response.
type SearchResponse struct {
	SchemaVersion string     `json:"schemaVersion"`
	Pairs         []PoolInfo `json:"pairs"`
	Pair          *PoolInfo  `json:"pair"`
}

// RecentSwapsResponse represents the recent swaps API response.
type RecentSwapsResponse struct {
	Schema string         `json:"schema"`
	Data   SwapsDataBlock `json:"data"`
}

// SwapsDataBlock contains the array of swap data from DexScreener.
type SwapsDataBlock struct {
	Swaps []SwapData `json:"swaps"`
}

// SwapData represents a single swap from DexScreener recent swaps API.
type SwapData struct {
	ID              string `json:"id"`
	PoolAddress     string `json:"poolAddress"`
	ChainID         string `json:"chainId"`
	DEX             string `json:"dexId"`
	Protocol        string `json:"protocolType"`
	Token0Symbol    string `json:"baseToken_symbol"`
	Token1Symbol    string `json:"quoteToken_symbol"`
	Token0Address   string `json:"baseToken_address"`
	Token1Address   string `json:"quoteToken_address"`
	Side            string `json:"side"` // "BUY" or "SELL"
	Amount          string `json:"amount"`
	TokenAmount0    string `json:"tokenAmount0"`
	TokenAmount1    string `json:"tokenAmount1"`
	VolumeUSD       string `json:"volumeUsd"`
	Price           string `json:"price"`
	PriceUSD        string `json:"priceUsd"`
	TxHash          string `json:"txHash"`
	BlockNumber     uint64 `json:"blockNumber"`
	BlockTimestamp  int64  `json:"blockTimestamp"`
	Gas             string `json:"gas"`
	GasPrice        string `json:"gasPrice"`
	IsBot           bool   `json:"isBot"`
	IsWhale         bool   `json:"isWhale"`
	IsInstitutional bool   `json:"isInstitutional"`
}

// SearchPools searches for pools by token pair on a chain.
func (c *Client) SearchPools(ctx context.Context, chainID, token0Address, token1Address string) ([]PoolInfo, error) {
	u, err := url.Parse(c.baseURL + "/latest/dex/pairs/" + chainID)
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

	var result SearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return result.Pairs, nil
}

// GetPoolByAddress retrieves pool info by pool address.
func (c *Client) GetPoolByAddress(ctx context.Context, chainID, poolAddress string) (*PoolInfo, error) {
	u, err := url.Parse(c.baseURL + "/latest/dex/pairs/" + chainID + "/" + poolAddress)
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

	var result SearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	if result.Pair != nil {
		return result.Pair, nil
	}
	if len(result.Pairs) > 0 {
		return &result.Pairs[0], nil
	}
	return nil, nil
}

// GetRecentSwaps retrieves recent swaps for a pool.
func (c *Client) GetRecentSwaps(ctx context.Context, chainID, poolAddress string) ([]SwapData, error) {
	u, err := url.Parse(c.baseURL + "/latest/dex/pairs/" + chainID + "/" + poolAddress + "/swaps")
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

	var result RecentSwapsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return result.Data.Swaps, nil
}

// GetTokenPrice fetches current price for a token from token lookup.
func (c *Client) GetTokenPrice(ctx context.Context, chainID, tokenAddress string) (decimal.Decimal, error) {
	u, err := url.Parse(c.baseURL + "/latest/dex/tokens/" + tokenAddress)
	if err != nil {
		return decimal.Zero, fmt.Errorf("parse URL: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return decimal.Zero, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return decimal.Zero, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return decimal.Zero, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var result struct {
		SchemaVersion string     `json:"schemaVersion"`
		Pairs         []PoolInfo `json:"pairs"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return decimal.Zero, fmt.Errorf("decode response: %w", err)
	}

	// Get the pool with highest liquidity
	var bestPool *PoolInfo
	var maxLiquidity decimal.Decimal
	for i := range result.Pairs {
		pool := &result.Pairs[i]
		liquidity, _ := decimal.NewFromString(pool.Liquidity.USD.String())
		if liquidity.GreaterThan(maxLiquidity) {
			maxLiquidity = liquidity
			bestPool = pool
		}
	}

	if bestPool == nil {
		return decimal.Zero, nil
	}

	priceUSD, err := decimal.NewFromString(bestPool.PriceUSD)
	if err != nil {
		return decimal.Zero, fmt.Errorf("parse price: %w", err)
	}

	return priceUSD, nil
}

// HealthCheck verifies the DexScreener API is accessible.
func (c *Client) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/latest/ping", nil)
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

// sanitizePoolAddress ensures pool address has 0x prefix.
func sanitizePoolAddress(addr string) string {
	if !strings.HasPrefix(addr, "0x") && !strings.HasPrefix(addr, "0X") {
		return "0x" + addr
	}
	return strings.ToLower(addr)
}
