//go:build live

package main

import (
	"context"
	"fmt"
	"math/big"
	"path/filepath"
	"strings"
	"sync/atomic"

	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	flashbotsprotect "github.com/lpbot/lpbot/internal/adapters/mev/flashbots-protect"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	keystorewallet "github.com/lpbot/lpbot/internal/adapters/wallet/keystore"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

func configureLiveExecution(ctx context.Context, app *App, orderManager *orderManagerAdapter) error {
	if app == nil || app.config == nil || orderManager == nil || app.liveGate == nil {
		return nil
	}
	if !app.liveGate.isExecutionMode() || !liveExecutionPathAvailable(app.config) {
		return nil
	}

	wallet, err := openLiveWallet(ctx, app)
	if err != nil {
		if app.liveGate.enabled {
			return fmt.Errorf("open live wallet: %w", err)
		}
		app.logger.Warn("live wallet not opened because live is disabled", zap.Error(err))
		return nil
	}

	broadcaster, transport, err := buildLiveBroadcaster(ctx, app)
	if err != nil {
		_ = wallet.Close()
		if app.liveGate.enabled {
			return fmt.Errorf("initialize live broadcaster: %w", err)
		}
		app.logger.Warn("live broadcaster not initialized because live is disabled", zap.Error(err))
		return nil
	}

	orderManager.wallet = wallet
	orderManager.broadcaster = broadcaster
	orderManager.requiredConfs = app.config.Chains.Base.Confirmations
	app.liveGate.executionBackendWired = true
	app.logger.Info("live execution path wired",
		zap.String("backend", app.liveGate.executionBackend),
		zap.String("transport", transport),
		zap.String("wallet", maskAddress(wallet.Address().String())),
		zap.String("base_rpc", sanitizeEndpointForLog(liveBaseRPCURL(app))))
	return nil
}

func buildLiveBroadcaster(ctx context.Context, app *App) (ports.Broadcaster, string, error) {
	if app == nil {
		return nil, "", fmt.Errorf("app is nil")
	}
	return buildLiveBroadcasterWithRuntime(ctx, app.config, app.rpc["base"], app.logger)
}

func buildLiveBroadcasterWithRuntime(ctx context.Context, cfg *config.Config, baseProvider *rpc.RoundRobinProvider, logger *zap.Logger) (ports.Broadcaster, string, error) {
	if cfg == nil {
		return nil, "", fmt.Errorf("config is nil")
	}
	baseCfg := cfg.Chains.Base
	mevMode := strings.TrimSpace(baseCfg.MEV)
	mevEndpoint := strings.TrimSpace(baseCfg.MEVEndpoint)
	if mevMode == "flashbots-protect" && baseCfg.MEVStrict && mevEndpoint == "" {
		return nil, "", fmt.Errorf("chains.base.mev_strict=true but chains.base.mev_endpoint is empty")
	}
	if mevMode == "flashbots-protect" && baseCfg.MEVStrict {
		submitter, err := flashbotsprotect.NewFlashbotsMEVStrict(flashbotsprotect.StrictConfig{
			StrictMode:          true,
			BundleEndpoint:      mevEndpoint,
			FallbackBroadcaster: nil,
			Logger:              logger,
		})
		if err != nil {
			return nil, "", err
		}
		return &mevBroadcaster{submitter: submitter}, "flashbots-protect", nil
	}

	baseRPCURL := strings.TrimSpace(cfg.Chains.Base.RPCPrimary)
	if baseRPCURL == "" && baseProvider != nil {
		baseRPCURL = baseProvider.Endpoint()
	}
	publicBroadcaster, err := livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:          baseRPCURL,
		SolanaRPCURL:        strings.TrimSpace(cfg.Chains.Solana.RPCPrimary),
		Confirmations:       cfg.Chains.Base.Confirmations,
		SolanaSkipPreflight: cfg.Chains.Solana.SkipPreflight,
	})
	if err != nil {
		return nil, "", err
	}

	if mevMode != "flashbots-protect" {
		return publicBroadcaster, "public-rpc", nil
	}
	if mevEndpoint == "" {
		return publicBroadcaster, "public-rpc", nil
	}

	submitter, err := flashbotsprotect.NewFlashbotsMEVStrict(flashbotsprotect.StrictConfig{
		StrictMode:          baseCfg.MEVStrict,
		BundleEndpoint:      mevEndpoint,
		FallbackBroadcaster: publicBroadcaster,
		Logger:              logger,
	})
	if err != nil {
		return nil, "", err
	}

	return &mevBroadcaster{submitter: submitter}, "flashbots-protect", nil
}

func openLiveWallet(ctx context.Context, app *App) (ports.Wallet, error) {
	keystorePath := strings.TrimSpace(app.config.Wallet.KeystorePath)
	if keystorePath == "" {
		return nil, fmt.Errorf("wallet.keystore_path is empty")
	}
	walletAddress := parseAddressOrZero(strings.TrimSpace(app.config.Live.WalletAddress))
	if walletAddress.IsZero() {
		return nil, fmt.Errorf("live.wallet_address is empty")
	}

	cfg := ports.WalletConfig{
		Type:         "keystore",
		ChainID:      domain.ChainBase,
		KeystoreDir:  filepath.Dir(keystorePath),
		KeystoreFile: filepath.Base(keystorePath),
		Passphrase:   app.config.Wallet.Passphrase,
		Address:      walletAddress,
	}
	provider, err := keystorewallet.New(ctx, cfg)
	if err != nil {
		return nil, err
	}
	baseProvider := app.rpc["base"]
	if baseProvider == nil {
		return nil, fmt.Errorf("base rpc provider not configured")
	}
	provider.SetRPCProvider(baseProvider)
	provider.SetChain(baseProvider)
	provider.SetGasOracle(roundRobinGasOracle{provider: baseProvider})
	return provider.Open(ctx, cfg)
}

func liveBaseRPCURL(app *App) string {
	if app == nil || app.config == nil {
		return ""
	}
	if primary := strings.TrimSpace(app.config.Chains.Base.RPCPrimary); primary != "" {
		return primary
	}
	if provider := app.rpc["base"]; provider != nil {
		return provider.Endpoint()
	}
	return ""
}

type roundRobinGasOracle struct {
	provider *rpc.RoundRobinProvider
}

func (o roundRobinGasOracle) SuggestGasTip(ctx context.Context) (*big.Int, error) {
	if o.provider == nil {
		return nil, fmt.Errorf("base rpc provider not configured")
	}
	return o.provider.SuggestGasTipCap(ctx)
}

type mevBroadcaster struct {
	submitter ports.MEVSubmitter
	callCount atomic.Int64
}

func (b *mevBroadcaster) Send(ctx context.Context, tx domain.SignedTx) error {
	b.callCount.Add(1)
	if b.submitter == nil {
		return fmt.Errorf("mev submitter not configured")
	}
	_, err := b.submitter.Submit(ctx, tx, ports.MEVSubmitOpts{})
	return err
}

func (b *mevBroadcaster) CallCount() int64 {
	return b.callCount.Load()
}

func (b *mevBroadcaster) submissionStatus() domain.TxStatus {
	return domain.TxSubmittedPrivate
}

func (b *mevBroadcaster) confirmsOnSend() bool {
	return false
}
