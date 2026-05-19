// Package subgraph provides a subgraph datasource adapter for Base Uniswap V3.
//
// This adapter fetches historical pool states, swaps, and collected fees
// from The Graph Uniswap V3 subgraph on Base network.
package subgraph

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/shopspring/decimal"
)

// Client handles HTTP communication with Uniswap V3 subgraph.
type Client struct {
	client       *http.Client
	subgraphURL  string
}

// NewClient creates a new Uniswap V3 Subgraph client for Base network.
func NewClient() *Client {
	return &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		subgraphURL: "https://api.thegraph.com/subgraphs/name/ianolowitz/base-uniswap-v3",
	}
}

// NewClientWithURL creates a client with a custom subgraph endpoint.
func NewClientWithURL(url string) *Client {
	return &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		subgraphURL: url,
	}
}

// GraphQLRequest represents a GraphQL query request.
type GraphQLRequest struct {
	Query         string                  `json:"query"`
	OperationName string                 `json:"operationName,omitempty"`
	Variables     map[string]interface{} `json:"variables,omitempty"`
}

// GraphQLResponse represents a GraphQL response wrapper.
type GraphQLResponse struct {
	Data   json.RawMessage `json:"data,omitempty"`
	Errors []GraphQLError  `json:"errors,omitempty"`
}

// GraphQLError represents a GraphQL error.
type GraphQLError struct {
	Message string `json:"message"`
}

// PoolEntity represents a pool entity from the subgraph.
type PoolEntity struct {
	ID string `json:"id"`
	FeeGrowthInsideLast struct {
		Token0 string `json:"token0"`
		Token1 string `json:"token1"`
	} `json:"feeGrowthInsideLast"`
	FeeGrowthGlobal struct {
		Token0 string `json:"token0"`
		Token1 string `json:"token1"`
	} `json:"feeGrowthGlobal"`
	CollectedFeesToken0 string `json:"collectedFeesToken0"`
	CollectedFeesToken1 string `json:"collectedFeesToken1"`
	Tick               string `json:"tick"`
	SqrtPriceX96       string `json:"sqrtPriceX96"`
	Liquidity          string `json:"liquidity"`
	Token0             struct {
		ID       string `json:"id"`
		Symbol   string `json:"symbol"`
		Decimals string `json:"decimals"`
	} `json:"token0"`
	Token1 struct {
		ID       string `json:"id"`
		Symbol   string `json:"symbol"`
		Decimals string `json:"decimals"`
	} `json:"token1"`
	VolumeToken0 string `json:"volumeToken0"`
	VolumeToken1 string `json:"volumeToken1"`
	VolumeUSD    string `json:"volumeUSD"`
	TxCount      string `json:"txCount"`
	BlockNumber  string `json:"blockNumber"`
	Timestamp    string `json:"timestamp"`
}

// SwapEntity represents a swap entity from the subgraph.
type SwapEntity struct {
	ID      string `json:"id"`
	Pool    struct {
		ID string `json:"id"`
	} `json:"pool"`
	Token0  struct {
		ID       string `json:"id"`
		Symbol   string `json:"symbol"`
		Decimals string `json:"decimals"`
	} `json:"token0"`
	Token1 struct {
		ID       string `json:"id"`
		Symbol   string `json:"symbol"`
		Decimals string `json:"decimals"`
	} `json:"token1"`
	Amount0    string `json:"amount0"`
	Amount1    string `json:"amount1"`
	AmountUSD  string `json:"amountUSD"`
	Tick       string `json:"tick"`
	SqrtPriceX96 string `json:"sqrtPriceX96"`
	Recipient  string `json:"recipient"`
	Sender     string `json:"sender"`
	Origin     string `json:"origin"`
	BlockNumber string `json:"blockNumber"`
	Timestamp  string `json:"timestamp"`
	GasUsed    string `json:"gasUsed"`
	GasPrice   string `json:"gasPrice"`
}

// FeeQueryResult represents the result of a fees query.
type FeeQueryResult struct {
	Pools []PoolEntity `json:"pools"`
}

// SwapsQueryResult represents the result of a swaps query.
type SwapsQueryResult struct {
	Swaps []SwapEntity `json:"swaps"`
}

// QueryCollectedFees queries total collected fees for a pool.
func (c *Client) QueryCollectedFees(ctx context.Context, poolAddress string, from, to time.Time) (token0Fees, token1Fees decimal.Decimal, err error) {
	query := `query GetCollectedFees($pool: String!, $from: Int!, $to: Int!) {
		pools(where: { id: $pool }) {
			id
			collectedFeesToken0
			collectedFeesToken1
			feeGrowthGlobal {
				token0
				token1
			}
		}
	}`

	variables := map[string]interface{}{
		"pool": strings.ToLower(poolAddress),
		"from": from.Unix(),
		"to":   to.Unix(),
	}

	result, err := c.executeQuery(ctx, query, variables)
	if err != nil {
		return decimal.Zero, decimal.Zero, err
	}

	var feeResult FeeQueryResult
	if err := json.Unmarshal(result, &feeResult); err != nil {
		return decimal.Zero, decimal.Zero, fmt.Errorf("unmarshal result: %w", err)
	}

	if len(feeResult.Pools) == 0 {
		return decimal.Zero, decimal.Zero, nil
	}

	pool := feeResult.Pools[0]

	token0Fees, _ = decimal.NewFromString(pool.CollectedFeesToken0)
	token1Fees, _ = decimal.NewFromString(pool.CollectedFeesToken1)

	return token0Fees, token1Fees, nil
}

// QuerySwaps queries historical swaps for a pool.
func (c *Client) QuerySwaps(ctx context.Context, poolAddress string, from, to time.Time, limit int) ([]SwapEntity, error) {
	if limit <= 0 {
		limit = 1000
	}

	query := `query GetSwaps($pool: String!, $from: Int!, $to: Int!, $limit: Int!) {
		swaps(
			where: { pool: $pool, timestamp_gte: $from, timestamp_lte: $to }
			orderBy: timestamp
			orderDirection: asc
			first: $limit
		) {
			id
			pool {
				id
			}
			token0 {
				id
				symbol
				decimals
			}
			token1 {
				id
				symbol
				decimals
			}
			amount0
			amount1
			amountUSD
			tick
			sqrtPriceX96
			recipient
			sender
			origin
			blockNumber
			timestamp
			gasUsed
			gasPrice
		}
	}`

	variables := map[string]interface{}{
		"pool":  strings.ToLower(poolAddress),
		"from":  from.Unix(),
		"to":    to.Unix(),
		"limit": limit,
	}

	result, err := c.executeQuery(ctx, query, variables)
	if err != nil {
		return nil, err
	}

	var swapsResult SwapsQueryResult
	if err := json.Unmarshal(result, &swapsResult); err != nil {
		return nil, fmt.Errorf("unmarshal result: %w", err)
	}

	return swapsResult.Swaps, nil
}

// executeQuery executes a GraphQL query against the subgraph.
func (c *Client) executeQuery(ctx context.Context, query string, variables map[string]interface{}) (json.RawMessage, error) {
	reqBody := GraphQLRequest{
		Query:     query,
		Variables: variables,
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.subgraphURL, strings.NewReader(string(body)))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	var gqlResp GraphQLResponse
	if err := json.NewDecoder(resp.Body).Decode(&gqlResp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	if len(gqlResp.Errors) > 0 {
		return nil, fmt.Errorf("GraphQL error: %s", gqlResp.Errors[0].Message)
	}

	return gqlResp.Data, nil
}

// HealthCheck verifies the subgraph endpoint is accessible.
func (c *Client) HealthCheck(ctx context.Context) error {
	query := `{ __schema { queryType { name } } }`

	result, err := c.executeQuery(ctx, query, nil)
	if err != nil {
		return err
	}

	if len(result) == 0 {
		return fmt.Errorf("empty response from subgraph")
	}

	return nil
}