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

func Test_ModeMismatchReturnsError(t *testing.T) {
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

	_, err = Load(configPath, "dryrun")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mode mismatch")
}

func Test_ModeMatchLoads(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	err := os.WriteFile(configPath, []byte(`
[mode]
expected = "dryrun"

[platform]
log_level = "debug"
`), 0644)
	require.NoError(t, err)

	cfg, err := Load(configPath, "dryrun")
	require.NoError(t, err)
	assert.Equal(t, "dryrun", cfg.Mode.Expected)
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

func Test_EnvInterpolationMissingVarFailsClosed(t *testing.T) {
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

	_, err = Load(configPath, "dryrun")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing required environment variable")
	assert.Contains(t, err.Error(), "NONEXISTENT_VAR_12345")
}

func Test_EnvInterpolationOptionalDefaultValue(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	configContent := `
[mode]
expected = "dryrun"

[platform]
dashboard_token = "${MISSING_DASHBOARD_TOKEN:-disabled}"

[chains.base]
rpc_primary = "${BASE_RPC_PRIMARY:-https://mainnet.base.org}"
mev = "flashbots-protect"
mev_strict = true
`
	require.NoError(t, os.WriteFile(configPath, []byte(configContent), 0644))

	cfg, err := Load(configPath, "dryrun")
	require.NoError(t, err)
	assert.Equal(t, "disabled", cfg.Platform.DashboardToken)
	assert.Equal(t, "https://mainnet.base.org", cfg.Chains.Base.RPCPrimary)
	assert.True(t, cfg.Chains.Base.MEVStrict)
}

func Test_EnvInterpolationOptionalEmptyValue(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.toml")
	configContent := `
[mode]
expected = "dryrun"

[redis]
url = "${MISSING_REDIS_URL:-}"
`
	require.NoError(t, os.WriteFile(configPath, []byte(configContent), 0644))

	cfg, err := Load(configPath, "dryrun")
	require.NoError(t, err)
	assert.Equal(t, "", cfg.Redis.URL)
}

func Test_SHA256MismatchReturnsError(t *testing.T) {
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

	_, err = Load(configPath, "live")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "sha256 mismatch")
}

func Test_SHA256MatchLoads(t *testing.T) {
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

	cfg, err := Load(configPath, "live")
	require.NoError(t, err)
	assert.Equal(t, "live", cfg.Mode.Expected)
}

func Test_SHA256UsesInterpolatedContent(t *testing.T) {
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.live.toml")
	sha256Path := filepath.Join(tmpDir, "config.live.toml.sha256")

	configContent := `
[mode]
expected = "live"

[store]
postgres_dsn = "${TEST_POSTGRES_DSN}"
`
	require.NoError(t, os.WriteFile(configPath, []byte(configContent), 0644))

	os.Setenv("TEST_POSTGRES_DSN", "postgres://user:pass@db.internal/lpbot")
	defer os.Unsetenv("TEST_POSTGRES_DSN")

	effective := `
[mode]
expected = "live"

[store]
postgres_dsn = "postgres://user:pass@db.internal/lpbot"
`
	hash := sha256.Sum256([]byte(effective))
	require.NoError(t, os.WriteFile(sha256Path, []byte(fmt.Sprintf("%x\n", hash)), 0644))

	cfg, err := Load(configPath, "live")
	require.NoError(t, err)
	assert.Equal(t, "postgres://user:pass@db.internal/lpbot", cfg.Store.PostgresDSN)
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
