//go:build live

package main

import (
	"context"
	"fmt"
	"math/big"
	"os"
	"strings"
	"time"

	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

const canaryPrepareConfirmEnv = "LPBOT_CONFIRM_CANARY_PREPARE"

func runCanaryPrepare(ctx context.Context, cfg *config.Config) (err error) {
	if os.Getenv(canaryPrepareConfirmEnv) != "YES" {
		return fmt.Errorf("canary prepare requires %s=YES", canaryPrepareConfirmEnv)
	}
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()
	poolID := ""
	walletAddress := ""
	defer func() {
		if err != nil {
			_ = state.Record(ctx, canaryEvent{
				Command:  "canary_prepare",
				Stage:    "failed",
				Status:   "failed",
				PoolID:   poolID,
				Wallet:   walletAddress,
				ErrorMsg: err.Error(),
			})
		}
	}()
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_prepare",
		Stage:   "started",
		Status:  "running",
		Message: "manual canary prepare command started",
	}); err != nil {
		return err
	}
	gate := newLiveSafetyGate("live", cfg)
	if err := gate.requireManualCanary("canary prepare"); err != nil {
		return err
	}
	if len(cfg.Live.AllowedPools) != 1 {
		return fmt.Errorf("canary prepare requires exactly one allowed pool, got %d", len(cfg.Live.AllowedPools))
	}

	provider, err := newCanaryPreflightProvider(ctx, cfg)
	if err != nil {
		return err
	}
	wallet, err := openCanaryPreflightWallet(ctx, cfg, provider)
	if err != nil {
		return err
	}
	defer wallet.Close()
	walletAddress = wallet.Address().String()

	broadcaster, err := newCanaryPrepareBroadcaster(ctx, cfg, provider)
	if err != nil {
		return err
	}

	amountUSD, err := selectCanaryAmountUSD(cfg)
	if err != nil {
		return err
	}
	pool, err := loadCanaryPreflightPool(ctx, provider, strings.TrimSpace(cfg.Live.AllowedPools[0]))
	if err != nil {
		return err
	}
	poolID = pool.ID
	if err := checkCanaryPreflightOpen(gate, pool, amountUSD); err != nil {
		return err
	}
	report, err := buildCanaryPreflightReport(ctx, cfg, provider, wallet, pool, amountUSD)
	if err != nil {
		return err
	}
	printCanaryPreflightReport(report)
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_prepare",
		Stage:           "preflight_ok",
		Status:          "ok",
		PoolID:          pool.ID,
		Wallet:          wallet.Address().String(),
		AmountUSD:       amountUSD.String(),
		RequiredUSDCRaw: report.RequiredUSDC.String(),
		RequiredWETHRaw: report.RequiredWETH.String(),
		GasEstimate:     report.WrapGas + report.USDCApprovalGas + report.WETHApprovalGas,
		Message:         "prepare preflight completed",
	}); err != nil {
		return err
	}

	spender := parseAddressOrZero(strings.TrimSpace(cfg.Execution.NPMBaseAddress))
	if spender.IsZero() {
		return fmt.Errorf("npm base address is invalid")
	}
	if report.WrapRequiredWei.Sign() > 0 {
		if err := sendCanaryPrepareWrap(ctx, provider, wallet, broadcaster, state, pool, report.WrapRequiredWei); err != nil {
			return err
		}
	}
	if report.USDCAllowance.Cmp(report.RequiredUSDC) < 0 {
		if err := sendCanaryPrepareApproval(ctx, provider, wallet, broadcaster, state, pool, domain.MustParseAddress(baseUSDCAddress), spender, report.RequiredUSDC, "approve_usdc"); err != nil {
			return err
		}
	}
	if report.WETHAllowance.Cmp(report.RequiredWETH) < 0 {
		if err := sendCanaryPrepareApproval(ctx, provider, wallet, broadcaster, state, pool, domain.MustParseAddress(baseWETHAddress), spender, report.RequiredWETH, "approve_weth"); err != nil {
			return err
		}
	}
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_prepare",
		Stage:   "complete",
		Status:  "ok",
		PoolID:  pool.ID,
		Wallet:  wallet.Address().String(),
		Message: "canary prepare completed",
	}); err != nil {
		return err
	}
	fmt.Println("canary prepare complete")
	return nil
}

func newCanaryPrepareBroadcaster(ctx context.Context, cfg *config.Config, provider *rpc.RoundRobinProvider) (ports.Broadcaster, error) {
	baseRPCURL := strings.TrimSpace(cfg.Chains.Base.RPCPrimary)
	if baseRPCURL == "" && provider != nil {
		baseRPCURL = provider.Endpoint()
	}
	return livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:    baseRPCURL,
		Confirmations: cfg.Chains.Base.Confirmations,
	})
}

func sendCanaryPrepareWrap(ctx context.Context, provider *rpc.RoundRobinProvider, wallet ports.Wallet, broadcaster ports.Broadcaster, state *canaryEventWriter, pool domain.Pool, amountWei *big.Int) error {
	if amountWei == nil || amountWei.Sign() <= 0 {
		return nil
	}
	tx := domain.UnsignedTx{
		ID:       shadowID("canary-wrap-weth", pool.Key(), time.Now().Unix()),
		Chain:    domain.ChainBase,
		From:     wallet.Address(),
		To:       domain.MustParseAddress(baseWETHAddress),
		Data:     commonFromHexDeposit(),
		Value:    domain.MustDecimal(amountWei.String()),
		Deadline: time.Now().Add(5 * time.Minute).Unix(),
		MinOut:   domain.NewDecimalFromInt(1),
	}
	if _, err := estimatePreflightGas(ctx, provider, tx); err != nil {
		return fmt.Errorf("preflight wrap_weth: %w", err)
	}
	return signAndBroadcastCanaryPrepare(ctx, wallet, broadcaster, state, pool, tx, "wrap_weth")
}

func sendCanaryPrepareApproval(ctx context.Context, provider *rpc.RoundRobinProvider, wallet ports.Wallet, broadcaster ports.Broadcaster, state *canaryEventWriter, pool domain.Pool, token, spender domain.Address, amount *big.Int, action string) error {
	if amount == nil || amount.Sign() <= 0 {
		return nil
	}
	tx, err := wallet.ApproveExact(ctx, token, spender, amount)
	if err != nil {
		return fmt.Errorf("build %s: %w", action, err)
	}
	tx.ID = shadowID("canary-"+action, fmt.Sprintf("%s:%s", pool.Key(), token.String()), time.Now().Unix())
	tx.Deadline = time.Now().Add(5 * time.Minute).Unix()
	tx.MinOut = domain.NewDecimalFromInt(1)
	if _, err := estimatePreflightGas(ctx, provider, tx); err != nil {
		return fmt.Errorf("preflight %s: %w", action, err)
	}
	return signAndBroadcastCanaryPrepare(ctx, wallet, broadcaster, state, pool, tx, action)
}

func signAndBroadcastCanaryPrepare(ctx context.Context, wallet ports.Wallet, broadcaster ports.Broadcaster, state *canaryEventWriter, pool domain.Pool, tx domain.UnsignedTx, action string) error {
	signed, err := wallet.Sign(ctx, tx)
	if err != nil {
		return fmt.Errorf("sign %s: %w", action, err)
	}
	signed.ID = tx.ID
	signed.Status = domain.TxBuilt
	if err := state.RecordSignedTx(ctx, signed, domain.TxBuilt); err != nil {
		return fmt.Errorf("persist built %s tx: %w", action, err)
	}
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_prepare",
		Stage:   action + "_signed",
		Status:  "built",
		PoolID:  pool.ID,
		Wallet:  wallet.Address().String(),
		TxHash:  signed.Hash,
		Message: action + " transaction signed and persisted",
	}); err != nil {
		return err
	}
	if err := broadcaster.Send(ctx, signed); err != nil {
		return fmt.Errorf("broadcast %s: %w", action, err)
	}
	if err := state.RecordSignedTx(ctx, signed, domain.TxBroadcast); err != nil {
		return fmt.Errorf("persist broadcast %s tx: %w", action, err)
	}
	if err := state.Record(ctx, canaryEvent{
		Command: "canary_prepare",
		Stage:   action + "_broadcast",
		Status:  "broadcast",
		PoolID:  pool.ID,
		Wallet:  wallet.Address().String(),
		TxHash:  signed.Hash,
		Message: action + " transaction broadcast",
	}); err != nil {
		return err
	}
	fmt.Printf("tx_broadcast action=%s hash=%s\n", action, signed.Hash)
	return nil
}

func commonFromHexDeposit() []byte {
	return []byte{0xd0, 0xe3, 0x0d, 0xb0}
}
