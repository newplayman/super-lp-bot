package config

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Test_ModeMismatchPanic tests that Load panics when the config's mode.expected
// does not match the expectedMode parameter.
func Test_ModeMismatchPanic(t *testing.T) {
	// Create a temporary config file with mode.expected = "live"
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	err := os.WriteFile(configPath, []byte(`
[mode]
expected = "live"

[platform]
log_level = "info"
`), 0644)
	require.NoError(t, err)

	// Calling Load with expectedMode="dryrun" should panic
	assert.Panics(t, func() {
		Load(configPath, "dryrun")
	}, "Load should panic when mode.expected does not match expectedMode")
}

// Test_ModeMatchNoPanic tests that Load does not panic when modes match.
func Test_ModeMatchNoPanic(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	err := os.WriteFile(configPath, []byte(`
[mode]
expected = "dryrun"

[platform]
log_level = "debug"
`), 0644)
	require.NoError(t, err)

	// This should not panic
	require.NotPanics(t, func() {
		cfg, err := Load(configPath, "dryrun")
		require.NoError(t, err)
		assert.Equal(t, "dryrun", cfg.Mode.Expected)
	}, "Load should not panic when modes match")
}

// Test_EnvInterpolation tests that environment variables are correctly interpolated.
func Test_EnvInterpolation(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	configContent := `
[mode]
expected = "dryrun"

[platform]
log_level = "debug"

[chains.base]
rpc_primary = "${TEST_RPC_PRIMARY}"
rpc_fallback = ["${TEST_RPC_FALLBACK}"]
ws = "${TEST_WS}"

[store]
sqlite_path = "${TEST_SQLITE_PATH}"
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err)

	// Set environment variables
	os.Setenv("TEST_RPC_PRIMARY", "https://mainnet.base.org")
	os.Setenv("TEST_RPC_FALLBACK", "https://fallback.base.org")
	os.Setenv("TEST_WS", "wss://ws.base.org")
	os.Setenv("TEST_SQLITE_PATH", "/tmp/test.db")
	defer func() {
		os.Unsetenv("TEST_RPC_PRIMARY")
		os.Unsetenv("TEST_RPC_FALLBACK")
		os.Unsetenv("TEST_WS")
		os.Unsetenv("TEST_SQLITE_PATH")
	}()

	cfg, err := Load(configPath, "dryrun")
	require.NoError(t, err)

	assert.Equal(t, "https://mainnet.base.org", cfg.Chains.Base.RPCPrimary)
	assert.Equal(t, []string{"https://fallback.base.org"}, cfg.Chains.Base.RPCFallback)
	assert.Equal(t, "wss://ws.base.org", cfg.Chains.Base.WS)
	assert.Equal(t, "/tmp/test.db", cfg.Store.SQLitePath)
}

// Test_EnvInterpolationMissingVar tests that missing env vars result in empty string.
func Test_EnvInterpolationMissingVar(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	configContent := `
[mode]
expected = "dryrun"

[chains.base]
rpc_primary = "${NONEXISTENT_VAR_12345}"
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err)

	// NONEXISTENT_VAR_12345 is not set, so it should interpolate to empty string
	cfg, err := Load(configPath, "dryrun")
	require.NoError(t, err)
	assert.Equal(t, "", cfg.Chains.Base.RPCPrimary)
}

// Test_SHA256MismatchPanic tests that for live mode, sha256 checksum verification
// is performed and mismatches cause panic.
func Test_SHA256MismatchPanic(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.live.toml")
	sha256Path := filepath.Join(tmpDir, "config.live.toml.sha256")

	// Write a config file
	configContent := `
[mode]
expected = "live"

[platform]
log_level = "info"
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err)

	// Write a WRONG sha256 checksum (deliberately incorrect)
	err = os.WriteFile(sha256Path, []byte("deadbeefcafebabe0000000000000000000000000000000000000000000000\n"), 0644)
	require.NoError(t, err)

	// Loading live config with wrong sha256 should panic
	assert.Panics(t, func() {
		Load(configPath, "live")
	}, "Load should panic when sha256 checksum does not match")
}

// Test_SHA256MatchNoPanic tests that correct sha256 allows loading.
func Test_SHA256MatchNoPanic(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.live.toml")
	sha256Path := filepath.Join(tmpDir, "config.live.toml.sha256")

	configContent := `
[mode]
expected = "live"

[platform]
log_level = "info"
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err)

	// Compute correct sha256
	hash := sha256.Sum256([]byte(configContent))
	sha256Hex := fmt.Sprintf("%x\n", hash)
	err = os.WriteFile(sha256Path, []byte(sha256Hex), 0644)
	require.NoError(t, err)

	// This should not panic
	require.NotPanics(t, func() {
		cfg, err := Load(configPath, "live")
		require.NoError(t, err)
		assert.Equal(t, "live", cfg.Mode.Expected)
	}, "Load should not panic when sha256 matches")
}

// Test_LoadNonExistentFile tests that loading a non-existent file returns error.
func Test_LoadNonExistentFile(t *testing.T) {
	_, err := Load("/nonexistent/path/config.toml", "dryrun")
	assert.Error(t, err)
}

// Test_LoadInvalidTOML tests that loading invalid TOML returns error.
func Test_LoadInvalidTOML(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	err := os.WriteFile(configPath, []byte(`invalid toml content {[[[`), 0644)
	require.NoError(t, err)

	_, err = Load(configPath, "dryrun")
	assert.Error(t, err)
}

// Test_ShadowModeNoSHA256 tests that shadow mode does not require sha256.
func Test_ShadowModeNoSHA256(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")

	configContent := `
[mode]
expected = "shadow"

[platform]
log_level = "debug"
`
	err := os.WriteFile(configPath, []byte(configContent), 0644)
	require.NoError(t, err)

	// No sha256 file exists, but shadow mode should still work
	cfg, err := Load(configPath, "shadow")
	require.NoError(t, err)
	assert.Equal(t, "shadow", cfg.Mode.Expected)
}
