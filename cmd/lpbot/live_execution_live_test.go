//go:build live

package main

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"

	"github.com/lpbot/lpbot/internal/platform/config"
)

func TestBuildLiveBroadcaster_StrictMEVRequiresEndpoint(t *testing.T) {
	app := &App{
		logger: zap.NewNop(),
		config: &config.Config{
			Chains: config.Chains{
				Base: config.ChainConfig{
					RPCPrimary: "http://127.0.0.1:0",
					MEV:        "flashbots-protect",
					MEVStrict:  true,
				},
			},
		},
	}

	_, _, err := buildLiveBroadcaster(context.Background(), app)
	require.Error(t, err)
	require.Contains(t, err.Error(), "mev_endpoint is empty")
}

func TestBuildLiveBroadcasterWithRuntime_StrictMEVAvoidsPublicBroadcaster(t *testing.T) {
	cfg := &config.Config{
		Chains: config.Chains{
			Base: config.ChainConfig{
				MEV:         "flashbots-protect",
				MEVStrict:   true,
				MEVEndpoint: "https://flashbots.example",
			},
		},
	}

	broadcaster, transport, err := buildLiveBroadcasterWithRuntime(context.Background(), cfg, nil, zap.NewNop())
	require.NoError(t, err)
	require.Equal(t, "flashbots-protect", transport)
	require.IsType(t, &mevBroadcaster{}, broadcaster)
}

func TestPrivateMEVSubmissionDoesNotConfirmOnSend(t *testing.T) {
	status := txStatusAfterLiveSend(&mevBroadcaster{}, 10)
	require.Equal(t, domain.TxSubmittedPrivate, status)
	require.False(t, broadcasterConfirmsOnSend(&mevBroadcaster{}, 10))
}
