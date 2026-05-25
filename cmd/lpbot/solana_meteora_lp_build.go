package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/lpbot/lpbot/internal/platform/config"
)

type solanaMeteoraHelperResult struct {
	PoolID              string   `json:"poolId"`
	User                string   `json:"user"`
	PositionPubkey      string   `json:"positionPubkey"`
	ActiveBinID         int      `json:"activeBinId"`
	ActiveBinPrice      string   `json:"activeBinPrice"`
	MinBinID            int      `json:"minBinId"`
	MaxBinID            int      `json:"maxBinId"`
	StrategyType        string   `json:"strategyType"`
	TotalXAmountRaw     string   `json:"totalXAmountRaw"`
	TotalYAmountRaw     string   `json:"totalYAmountRaw"`
	InstructionCount    int      `json:"instructionCount"`
	FeePayer            string   `json:"feePayer"`
	RecentBlockhash     string   `json:"recentBlockhash"`
	TxBase64            string   `json:"txBase64"`
	SDKWarnings         []string `json:"sdkWarnings"`
	SimulationErr       any      `json:"simulationErr"`
	SimulationUnits     uint64   `json:"simulationUnits"`
	SimulationLogs      []string `json:"simulationLogs"`
	SimulationRPCError  string   `json:"simulationRpcError"`
	SimulationBlockhash string   `json:"simulationReplacementBlockhash"`
	BuildError          string   `json:"buildError"`
}

func runSolanaMeteoraLPBuildReadiness(ctx context.Context, cfg *config.Config, poolID string, userPublicKey string, totalUSD string, rangePct string, slippageBPS int, maxPriorityLamports uint64, reserveLamports uint64) error {
	preflight, err := buildSolanaMeteoraLPPreflightResult(ctx, cfg, poolID, userPublicKey, totalUSD, rangePct, slippageBPS, maxPriorityLamports, reserveLamports)
	if err != nil {
		return err
	}
	printSolanaMeteoraLPPreflight(preflight)
	if !preflight.Ready {
		fmt.Printf("solana_meteora_lp_build_readiness ready=false blocker=%q reason=%q\n", preflight.Blocker, "preflight_not_ready")
		return nil
	}
	helperResult, err := runSolanaMeteoraHelper(preflight, slippageBPS)
	if err != nil {
		return err
	}
	printSolanaMeteoraLPBuildResult(preflight, helperResult)
	return nil
}

func runSolanaMeteoraHelper(preflight solanaMeteoraLPPreflightResult, slippageBPS int) (solanaMeteoraHelperResult, error) {
	if len(preflight.Legs) < 2 {
		return solanaMeteoraHelperResult{}, fmt.Errorf("solana meteora helper requires two legs")
	}
	helperDir := filepath.Join("tools", "meteora-dlmm-helper")
	scriptPath := "open_position_readiness.cjs"
	if _, err := os.Stat(scriptPath); err != nil {
		if _, dirErr := os.Stat(filepath.Join(helperDir, scriptPath)); dirErr != nil {
			return solanaMeteoraHelperResult{}, fmt.Errorf("meteora helper script unavailable at %s: %w", filepath.Join(helperDir, scriptPath), dirErr)
		}
	}
	cmd := exec.Command("node", scriptPath,
		"--pool", preflight.PoolID,
		"--user", preflight.Wallet,
		"--lower-price", preflight.RangeLowerPrice.String(),
		"--upper-price", preflight.RangeUpperPrice.String(),
		"--amount-x-raw", strconv.FormatUint(preflight.Legs[0].TargetRaw, 10),
		"--amount-y-raw", strconv.FormatUint(preflight.Legs[1].TargetRaw, 10),
		"--slippage-pct", formatMeteoraSlippage(slippageBPS),
	)
	cmd.Dir = helperDir
	cmd.Env = os.Environ()
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err != nil {
		errText := strings.TrimSpace(stderr.String())
		if errText == "" {
			errText = strings.TrimSpace(stdout.String())
		}
		return solanaMeteoraHelperResult{}, fmt.Errorf("meteora helper failed: %w: %s", err, errText)
	}
	var result solanaMeteoraHelperResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return solanaMeteoraHelperResult{}, fmt.Errorf("decode meteora helper output: %w", err)
	}
	if extra := strings.TrimSpace(stderr.String()); extra != "" {
		result.SDKWarnings = append(result.SDKWarnings, extra)
	}
	return result, nil
}

func formatMeteoraSlippage(slippageBPS int) string {
	if slippageBPS <= 0 {
		return "1"
	}
	value := float64(slippageBPS) / 100
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func printSolanaMeteoraLPBuildResult(preflight solanaMeteoraLPPreflightResult, helper solanaMeteoraHelperResult) {
	buildReady := helper.BuildError == "" && helper.TxBase64 != ""
	simReady := helper.SimulationRPCError == "" && helper.SimulationErr == nil
	blocker := ""
	switch {
	case helper.BuildError != "":
		blocker = helper.BuildError
	case helper.SimulationRPCError != "":
		blocker = helper.SimulationRPCError
	case helper.SimulationErr != nil:
		blocker = fmt.Sprintf("%v", helper.SimulationErr)
	}
	fmt.Printf("solana_meteora_lp_build_readiness ready=%t sim_ready=%t blocker=%q position=%s active_bin_id=%d active_bin_price=%s min_bin_id=%d max_bin_id=%d ix_count=%d tx_base64_len=%d\n",
		buildReady,
		simReady,
		blocker,
		shortAddress(helper.PositionPubkey),
		helper.ActiveBinID,
		helper.ActiveBinPrice,
		helper.MinBinID,
		helper.MaxBinID,
		helper.InstructionCount,
		len(helper.TxBase64),
	)
	fmt.Printf("solana_meteora_lp_build_amounts token_x=%s amount_x_raw=%s token_y=%s amount_y_raw=%s fee_payer=%s recent_blockhash=%s budget_usd=%s\n",
		shortAddress(preflight.Token0),
		helper.TotalXAmountRaw,
		shortAddress(preflight.Token1),
		helper.TotalYAmountRaw,
		shortAddress(helper.FeePayer),
		shortAddress(helper.RecentBlockhash),
		preflight.TotalBudgetUSD.StringFixed(2),
	)
	if len(helper.SDKWarnings) > 0 {
		fmt.Printf("solana_meteora_lp_build_sdk_warnings count=%d first=%q\n", len(helper.SDKWarnings), helper.SDKWarnings[0])
	}
	if helper.SimulationErr != nil || helper.SimulationRPCError != "" {
		fmt.Printf("solana_meteora_lp_build_simulation ready=false err=%v rpc_error=%q units=%d replacement_blockhash=%s logs=%d\n",
			helper.SimulationErr,
			helper.SimulationRPCError,
			helper.SimulationUnits,
			shortAddress(helper.SimulationBlockhash),
			len(helper.SimulationLogs),
		)
		return
	}
	fmt.Printf("solana_meteora_lp_build_simulation ready=true units=%d replacement_blockhash=%s logs=%d\n",
		helper.SimulationUnits,
		shortAddress(helper.SimulationBlockhash),
		len(helper.SimulationLogs),
	)
}
