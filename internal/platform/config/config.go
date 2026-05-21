// Package config provides configuration loading with TOML support,
// environment variable interpolation, and mode-specific verification.
package config

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/pelletier/go-toml/v2"
)

// Mode represents the operation mode configuration.
type Mode struct {
	Expected string `toml:"expected"`
}

// Platform represents platform-level configuration.
type Platform struct {
	LogLevel       string `toml:"log_level"`
	MetricsAddr    string `toml:"metrics_addr"`
	DashboardToken string `toml:"dashboard_token"`
}

// ChainConfig represents a single chain's configuration.
type ChainConfig struct {
	RPCPrimary    string   `toml:"rpc_primary"`
	RPCFallback   []string `toml:"rpc_fallback"`
	WS            string   `toml:"ws"`
	MEV           string   `toml:"mev"`
	Confirmations int      `toml:"confirmations"`
	Commitment    string   `toml:"commitment"`
}

// Chains represents all chain configurations.
type Chains struct {
	Base   ChainConfig `toml:"base"`
	Solana ChainConfig `toml:"solana"`
}

// Store represents the storage configuration.
type Store struct {
	Backend     string `toml:"backend"`
	PostgresDSN string `toml:"postgres_dsn"`
	SQLitePath  string `toml:"sqlite_path"`
}

// Redis represents optional Redis runtime configuration.
type Redis struct {
	URL                      string `toml:"url"`
	Prefix                   string `toml:"prefix"`
	HeartbeatIntervalSeconds int    `toml:"heartbeat_interval_seconds"`
	HeartbeatTTLSeconds      int    `toml:"heartbeat_ttl_seconds"`
}

// Wallet represents the wallet configuration.
type Wallet struct {
	Backend      string `toml:"backend"`
	KeystorePath string `toml:"keystore_path"`
}

// Bus represents the bus configuration.
type Bus struct {
	Backend string `toml:"backend"`
}

// Execution represents execution backend configuration for live/canary mode.
type Execution struct {
	Backend        string `toml:"backend"`
	OKXAPIKey      string `toml:"okx_api_key"`
	OKXAPISecret   string `toml:"okx_api_secret"`
	OKXPassphrase  string `toml:"okx_api_passphrase"`
	OKXProjectID   string `toml:"okx_project_id"`
}

// Live represents the live execution safety configuration.
type Live struct {
	Enabled           bool     `toml:"enabled"`
	Canary            bool     `toml:"canary"`
	KillSwitch        bool     `toml:"kill_switch"`
	WalletAddress     string   `toml:"wallet_address"`
	AllowedChains     []string `toml:"allowed_chains"`
	AllowedPools      []string `toml:"allowed_pools"`
	MaxOrderUSD       float64  `toml:"max_order_usd"`
	DailyLossLimitUSD float64  `toml:"daily_loss_limit_usd"`
}

// Risk represents the risk configuration.
type Risk struct {
	TotalExposurePct  int `toml:"total_exposure_pct"`
	VarWarnPct        int `toml:"var_warn_pct"`
	VarKillPct        int `toml:"var_kill_pct"`
	DailyDDKillPct    int `toml:"daily_dd_kill_pct"`
	WeeklyDDFreezePct int `toml:"weekly_dd_freeze_pct"`
}

// TierConfig represents a tier configuration.
type TierConfig struct {
	MaxPerPoolUSD float64 `toml:"max_per_pool_usd"`
	ILStopPct     float64 `toml:"il_stop_pct"`
	RangeKSigma   float64 `toml:"range_k_sigma"`
	MinHoldHours  float64 `toml:"min_hold_hours"`
}

// Config represents the full application configuration.
type Config struct {
	Mode     Mode       `toml:"mode"`
	Platform Platform   `toml:"platform"`
	Chains   Chains     `toml:"chains"`
	Store    Store      `toml:"store"`
	Redis    Redis      `toml:"redis"`
	Wallet   Wallet     `toml:"wallet"`
	Bus      Bus        `toml:"bus"`
	Execution Execution `toml:"execution"`
	Live     Live       `toml:"live"`
	Risk     Risk       `toml:"risk"`
	TierA    TierConfig `toml:"tier_a"`
	TierB    TierConfig `toml:"tier_b"`
	TierC    TierConfig `toml:"tier_c"`
}

// Loader provides configuration loading functionality.
type Loader struct {
	// internal state if needed for future extensions
}

// envVarPattern matches ${ENV_VAR} pattern for environment variable interpolation.
var envVarPattern = regexp.MustCompile(`\$\{([^}]+)\}`)

// interpolateEnvVars replaces ${ENV_VAR} patterns with environment variable values.
// If an environment variable is not set, it is replaced with an empty string.
func interpolateEnvVars(data []byte) []byte {
	return envVarPattern.ReplaceAllFunc(data, func(match []byte) []byte {
		// Extract the variable name from ${VAR_NAME}
		varName := string(match[2 : len(match)-1]) // Remove ${ and }
		value := os.Getenv(varName)
		return []byte(value)
	})
}

// Load reads and parses a TOML configuration file from the given path.
// It performs environment variable interpolation and mode verification.
// For live mode, it also verifies the sha256 checksum against config.toml.sha256.
// Returns an error if the file cannot be read, contains invalid TOML,
// or if the mode mismatch panic is triggered.
func Load(path string, expectedMode string) (*Config, error) {
	// Read the raw config file
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	// Perform environment variable interpolation
	interpolated := interpolateEnvVars(data)

	// Parse TOML
	var cfg Config
	if err := toml.Unmarshal(interpolated, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse TOML: %w", err)
	}

	// Verify mode matches
	if cfg.Mode.Expected != expectedMode {
		panic(fmt.Sprintf("mode mismatch: config expects %q but expected %q", cfg.Mode.Expected, expectedMode))
	}

	// For live mode, verify sha256 checksum
	if expectedMode == "live" {
		if err := verifySHA256(path); err != nil {
			panic(err)
		}
	}

	return &cfg, nil
}

// verifySHA256 verifies that the config file matches the sha256 checksum
// stored in the .sha256 sidecar file.
func verifySHA256(configPath string) error {
	sha256Path := configPath + ".sha256"

	// Read the expected sha256 from the sidecar file
	expectedSHA256Hex, err := os.ReadFile(sha256Path)
	if err != nil {
		return fmt.Errorf("failed to read sha256 file: %w", err)
	}

	// Trim whitespace/newlines
	expectedSHA256Hex = []byte(strings.TrimSpace(string(expectedSHA256Hex)))

	// Read the current config file content
	configData, err := os.ReadFile(configPath)
	if err != nil {
		return fmt.Errorf("failed to read config for verification: %w", err)
	}

	// Compute sha256 of the config file
	hash := sha256.Sum256(configData)
	actualSHA256Hex := hex.EncodeToString(hash[:])

	// Compare
	if actualSHA256Hex != string(expectedSHA256Hex) {
		return fmt.Errorf("sha256 mismatch: config file has been modified (expected %s, got %s)",
			string(expectedSHA256Hex), actualSHA256Hex)
	}

	return nil
}
