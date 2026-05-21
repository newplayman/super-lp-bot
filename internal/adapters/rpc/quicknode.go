package rpc

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

const quickNodeAdminEndpoint = "https://api.quicknode.com/v0/endpoints?limit=50&offset=0"

type QuickNodeEndpoint struct {
	ID           string `json:"id"`
	Chain        string `json:"chain"`
	Network      string `json:"network"`
	HTTPURL      string `json:"http_url"`
	WSSURL       string `json:"wss_url"`
	IsMultichain bool   `json:"is_multichain"`
}

type quickNodeEndpointsResponse struct {
	Data []QuickNodeEndpoint `json:"data"`
}

func ResolveQuickNodeAPIKey() string {
	for _, key := range []string{"QUICKNODE_API_KEY", "QuicknodeAPI", "QUICKNODE_API"} {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}
	return ""
}

func DiscoverQuickNodeEndpoints(ctx context.Context, apiKey string, client *http.Client) ([]QuickNodeEndpoint, error) {
	if strings.TrimSpace(apiKey) == "" {
		return nil, nil
	}
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, quickNodeAdminEndpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("accept", "application/json")
	req.Header.Set("x-api-key", apiKey)

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("quicknode admin request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return nil, fmt.Errorf("quicknode admin api rejected key with status %d", resp.StatusCode)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("quicknode admin api returned status %d", resp.StatusCode)
	}

	var payload quickNodeEndpointsResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode quicknode admin response: %w", err)
	}
	return payload.Data, nil
}

func PickQuickNodeHTTPEndpoints(endpoints []QuickNodeEndpoint, chain string) []string {
	target := strings.ToLower(strings.TrimSpace(chain))
	out := make([]string, 0, len(endpoints))
	for _, endpoint := range endpoints {
		if strings.ToLower(strings.TrimSpace(endpoint.Chain)) != target {
			continue
		}
		if value := strings.TrimSpace(endpoint.HTTPURL); value != "" {
			out = append(out, value)
		}
	}
	return out
}

func PickQuickNodeWSURL(endpoints []QuickNodeEndpoint, chain string) string {
	target := strings.ToLower(strings.TrimSpace(chain))
	for _, endpoint := range endpoints {
		if strings.ToLower(strings.TrimSpace(endpoint.Chain)) != target {
			continue
		}
		if value := strings.TrimSpace(endpoint.WSSURL); value != "" {
			return value
		}
	}
	return ""
}
