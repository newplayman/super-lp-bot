//go:build live

package flashbotsprotect

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestMev_LiveBuildTag_ForcesStrictMode verifies that when compiled with the live tag,
// StrictMode is forced to true regardless of config.
func TestMev_LiveBuildTag_ForcesStrictMode(t *testing.T) {
	// This test only runs with the live build tag.
	// With live tag, strictModeForLive should be true.
	assert.True(t, strictModeForLive, "live build tag should set strictModeForLive to true")
}

// TestMev_LiveBuildTag_CreatorSetsStrict verifies that NewFlashbotsMEVStrict
// forces StrictMode=true when created with live tag.
func TestMev_LiveBuildTag_CreatorSetsStrict(t *testing.T) {
	// Config says strict=false, but live tag should force it to true
	cfg := StrictConfig{
		StrictMode:         false,
		BundleEndpoint:     "https://test.example.com",
		FallbackBroadcaster: nil,
	}

	submitter, err := NewFlashbotsMEVStrict(cfg)
	require.NoError(t, err)

	mevStrict, ok := submitter.(*flashbotsMEVStrict)
	require.True(t, ok)

	// With live build tag, StrictMode should be forced to true
	assert.True(t, mevStrict.cfg.StrictMode,
		"StrictMode should be forced to true by live build tag")
}