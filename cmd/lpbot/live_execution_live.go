//go:build live

package main

import (
	"context"
	"fmt"
	"math/big"
	"path/filepath"
	"strings"

	livebroadcast "github.com/lpbot/lpbot/internal/adapters/broadcast/live"
	"github.com/lpbot/lpbot/internal/adapters/rpc"
	keystorewallet "github.com/lpbot/lpbot/internal/adapters/wallet/keystore"
	"github.com/lpbot/lpbot/internal/domain"
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

	broadcaster, err := livebroadcast.New(ctx, livebroadcast.BroadcastConfig{
		BaseRPCURL:    liveBaseRPCURL(app),
		Confirmations: app.config.Chains.Base.Confirmations,
	})
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
		zap.String("wallet", maskAddress(wallet.Address().String())),
		zap.String("base_rpc", sanitizeEndpointForLog(liveBaseRPCURL(app))))
	return nil
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
