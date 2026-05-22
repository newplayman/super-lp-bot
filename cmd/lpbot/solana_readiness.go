package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	solrpc "github.com/lpbot/lpbot/internal/adapters/simulator/sol_rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaReadiness(ctx context.Context, cfg *config.Config) error {
	endpoint := solanaReadinessEndpoint(cfg)
	if endpoint == "" {
		return fmt.Errorf("solana rpc endpoint is empty")
	}
	fmt.Printf("solana_readiness endpoint=%s\n", redactRPCURL(endpoint))

	health, err := solanaJSONRPC(ctx, endpoint, "getHealth", []any{})
	if err != nil {
		return fmt.Errorf("getHealth: %w", err)
	}
	fmt.Printf("solana_health=%s\n", compactJSON(health))

	slot, err := solanaJSONRPC(ctx, endpoint, "getSlot", []any{map[string]any{"commitment": "processed"}})
	if err != nil {
		return fmt.Errorf("getSlot: %w", err)
	}
	fmt.Printf("solana_slot=%s\n", compactJSON(slot))

	blockhash, err := solanaJSONRPC(ctx, endpoint, "getLatestBlockhash", []any{map[string]any{"commitment": "processed"}})
	if err != nil {
		return fmt.Errorf("getLatestBlockhash: %w", err)
	}
	fmt.Printf("solana_latest_blockhash=%s\n", compactJSON(blockhash))

	fees, err := solanaJSONRPC(ctx, endpoint, "getRecentPrioritizationFees", []any{})
	if err != nil {
		fmt.Printf("solana_priority_fees=unavailable error=%q\n", err.Error())
	} else {
		fmt.Printf("solana_priority_fees=%s\n", compactJSON(fees))
	}

	feePayer := strings.TrimSpace(os.Getenv("SOLANA_FEE_PAYER_ADDRESS"))
	if feePayer == "" {
		fmt.Println("solana_simulate=skipped reason=missing_fee_payer env=SOLANA_FEE_PAYER_ADDRESS")
		return nil
	}

	from, err := domain.ParseAddress(feePayer)
	if err != nil {
		return fmt.Errorf("invalid SOLANA_FEE_PAYER_ADDRESS: %w", err)
	}
	if from.Chain() != domain.ChainSolana {
		return fmt.Errorf("SOLANA_FEE_PAYER_ADDRESS is not a solana address")
	}
	to := domain.MustParseAddress("So11111111111111111111111111111111111111112")
	fmt.Printf("solana_fee_payer=%s\n", shortAddress(from.String()))
	sim := solrpc.New(solrpc.Config{RPCEndpoint: endpoint})
	result, err := sim.Simulate(ctx, domain.UnsignedTx{
		ID:    "solana-readiness-simulate",
		Chain: domain.ChainSolana,
		From:  from,
		To:    to,
		Value: domain.NewDecimalFromInt(1),
	}, domain.BlockRef{Chain: domain.ChainSolana})
	if err != nil {
		return fmt.Errorf("simulateTransaction: %w", err)
	}
	fmt.Printf("solana_simulate success=%t gas_used=%d error=%q\n", result.Success, result.GasUsed, result.Error)
	if !result.Success {
		return fmt.Errorf("solana simulate failed: %s", result.Error)
	}
	return nil
}

func solanaReadinessEndpoint(cfg *config.Config) string {
	if cfg != nil {
		if endpoint := strings.TrimSpace(cfg.Chains.Solana.RPCPrimary); endpoint != "" {
			return endpoint
		}
		for _, endpoint := range cfg.Chains.Solana.RPCFallback {
			if strings.TrimSpace(endpoint) != "" {
				return strings.TrimSpace(endpoint)
			}
		}
	}
	return solrpc.DefaultRPCEndpoint
}

func solanaJSONRPC(ctx context.Context, endpoint string, method string, params []any) (json.RawMessage, error) {
	body, err := json.Marshal(map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  method,
		"params":  params,
	})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("content-type", "application/json")
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var decoded struct {
		Result json.RawMessage `json:"result"`
		Error  *struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		return nil, err
	}
	if decoded.Error != nil {
		return nil, fmt.Errorf("rpc error code=%d message=%s", decoded.Error.Code, decoded.Error.Message)
	}
	if len(decoded.Result) == 0 {
		return nil, fmt.Errorf("empty result")
	}
	return decoded.Result, nil
}

func compactJSON(raw json.RawMessage) string {
	var out bytes.Buffer
	if err := json.Compact(&out, raw); err != nil {
		return string(raw)
	}
	text := out.String()
	if len(text) > 360 {
		return text[:360] + "..."
	}
	return text
}

func redactRPCURL(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" {
		return "<redacted>"
	}
	parsed.User = nil
	if parsed.RawQuery != "" {
		parsed.RawQuery = "redacted=1"
	}
	parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
	if len(parts) > 0 && len(parts[0]) > 8 {
		parsed.Path = "/<redacted>/"
	}
	return parsed.String()
}

func shortAddress(address string) string {
	if len(address) <= 12 {
		return address
	}
	return address[:6] + "..." + address[len(address)-4:]
}
