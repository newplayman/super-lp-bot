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
	MEVEndpoint   string   `toml:"mev_endpoint"`
	MEVStrict     bool     `toml:"mev_strict"`
	Confirmations int      `toml:"confirmations"`
	Commitment    string   `toml:"commitment"`
	SkipPreflight bool     `toml:"skip_preflight"`
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
	Passphrase   string `toml:"passphrase"`
}

// Bus represents the bus configuration.
type Bus struct {
	Backend string `toml:"backend"`
}

// Alerting represents alert routing configuration.
type Alerting struct {
	TelegramToken      string `toml:"telegram_token"`
	TelegramChatID     string `toml:"telegram_chat_id"`
	MinIntervalSeconds int    `toml:"min_interval_seconds"`
}

// Execution represents execution backend configuration for live/canary mode.
type Execution struct {
	Backend             string `toml:"backend"`
	OKXAPIKey           string `toml:"okx_api_key"`
	OKXAPISecret        string `toml:"okx_api_secret"`
	OKXPassphrase       string `toml:"okx_api_passphrase"`
	OKXProjectID        string `toml:"okx_project_id"`
	NPMBaseAddress      string `toml:"npm_base_address"`
	TxDeadlineSeconds   int    `toml:"tx_deadline_seconds"`
	ExitDeadlineSeconds int    `toml:"exit_deadline_seconds"`
	SignTimeoutSeconds  int    `toml:"sign_timeout_seconds"`
	SendTimeoutSeconds  int    `toml:"send_timeout_seconds"`
	MintSlippageBps     int    `toml:"mint_slippage_bps"`
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

// LiveRisk represents live portfolio exposure and reconciliation guardrails.
type LiveRisk struct {
	MaxTotalExposureUSD             float64 `toml:"max_total_exposure_usd"`
	MaxPendingExposureUSD           float64 `toml:"max_pending_exposure_usd"`
	MaxSubmittedPrivateExposureUSD  float64 `toml:"max_submitted_private_exposure_usd"`
	MinGasReserveWei                string  `toml:"min_gas_reserve_wei"`
	MaxUnreconciledOpeningAgeSeconds int    `toml:"max_unreconciled_opening_age_seconds"`
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
	Mode      Mode       `toml:"mode"`
	Platform  Platform   `toml:"platform"`
	Chains    Chains     `toml:"chains"`
	Store     Store      `toml:"store"`
	Redis     Redis      `toml:"redis"`
	Wallet    Wallet     `toml:"wallet"`
	Bus       Bus        `toml:"bus"`
	Alerting  Alerting   `toml:"alerting"`
	Execution Execution  `toml:"execution"`
	Live      Live       `toml:"live"`
	LiveRisk  LiveRisk   `toml:"live_risk"`
	Risk      Risk       `toml:"risk"`
	TierA     TierConfig `toml:"tier_a"`
	TierB     TierConfig `toml:"tier_b"`
	TierC     TierConfig `toml:"tier_c"`
}

// Loader provides configuration loading functionality.
type Loader struct {
	// internal state if needed for future extensions
}

// envVarPattern matches ${ENV_VAR} pattern for environment variable interpolation.
var envVarPattern = regexp.MustCompile(`\$\{([^}]+)\}`)

func resolveEnvValue(varName string, lookup func(string) string) string {
	value := lookup(varName)
	if value != "" {
		return value
	}
	switch varName {
	case "POSTGRES_DSN":
		return lookup("DATABASE_URL")
	case "DATABASE_URL":
		return lookup("POSTGRES_DSN")
	default:
		return ""
	}
}

type envExpr struct {
	name            string
	defaultValue    string
	hasDefault      bool
	explicitRequire bool
}

func parseEnvExpr(raw string) envExpr {
	expr := envExpr{name: raw}
	if name, fallback, ok := strings.Cut(raw, ":-"); ok {
		expr.name = name
		expr.defaultValue = fallback
		expr.hasDefault = true
		return expr
	}
	if strings.HasSuffix(raw, "?") {
		expr.name = strings.TrimSuffix(raw, "?")
		expr.explicitRequire = true
	}
	return expr
}

func resolveEnvExpr(expr envExpr, lookup func(string) string) (string, bool) {
	if value := resolveEnvValue(expr.name, lookup); value != "" {
		return value, true
	}
	if expr.hasDefault {
		return expr.defaultValue, true
	}
	return "", false
}

func interpolateEnvVarsWithLookup(data []byte, lookup func(string) string) ([]byte, error) {
	matches := envVarPattern.FindAllSubmatch(data, -1)
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		expr := parseEnvExpr(string(match[1]))
		if _, ok := resolveEnvExpr(expr, lookup); !ok {
			return nil, fmt.Errorf("missing required environment variable %q", expr.name)
		}
	}

	interpolated := envVarPattern.ReplaceAllFunc(data, func(match []byte) []byte {
		expr := parseEnvExpr(string(match[2 : len(match)-1]))
		value, _ := resolveEnvExpr(expr, lookup)
		return []byte(value)
	})
	return interpolated, nil
}

// interpolateEnvVars replaces ${ENV_VAR} patterns with environment variable values.
func interpolateEnvVars(data []byte) ([]byte, error) {
	return interpolateEnvVarsWithLookup(data, os.Getenv)
}

// Load reads and parses a TOML configuration file from the given path.
// It performs environment variable interpolation and mode verification.
// For live mode, it also verifies the sha256 checksum against config.toml.sha256.
// Returns an error if the file cannot be read, contains invalid TOML,
// or if the mode mismatch panic is triggered.
func Load(path string, expectedMode string) (*Config, error) {
	return LoadWithLookup(path, expectedMode, os.Getenv)
}

// LoadWithEnvMap parses a TOML configuration file using the provided env map for interpolation.
func LoadWithEnvMap(path string, expectedMode string, env map[string]string) (*Config, error) {
	lookup := func(key string) string {
		if value, ok := env[key]; ok && value != "" {
			return value
		}
		return os.Getenv(key)
	}
	return LoadWithLookup(path, expectedMode, lookup)
}

// LoadWithLookup reads and parses a TOML configuration file using the provided lookup.
func LoadWithLookup(path string, expectedMode string, lookup func(string) string) (*Config, error) {
	// Read the raw config file
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	// Perform environment variable interpolation
	interpolated, err := interpolateEnvVarsWithLookup(data, lookup)
	if err != nil {
		return nil, err
	}

	// Parse TOML
	var cfg Config
	if err := toml.Unmarshal(interpolated, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse TOML: %w", err)
	}

	// Verify mode matches
	if cfg.Mode.Expected != expectedMode {
		return nil, fmt.Errorf("mode mismatch: config expects %q but expected %q", cfg.Mode.Expected, expectedMode)
	}

	// For live mode, verify sha256 checksum
	if expectedMode == "live" {
		if err := verifySHA256(path, interpolated); err != nil {
			return nil, err
		}
	}

	return &cfg, nil
}

// verifySHA256 verifies that the config file matches the sha256 checksum
// stored in the .sha256 sidecar file.
func verifySHA256(configPath string, effectiveConfig []byte) error {
	sha256Path := configPath + ".sha256"

	// Read the expected sha256 from the sidecar file
	expectedSHA256Hex, err := os.ReadFile(sha256Path)
	if err != nil {
		return fmt.Errorf("failed to read sha256 file: %w", err)
	}

	// Trim whitespace/newlines
	expectedSHA256Hex = []byte(strings.TrimSpace(string(expectedSHA256Hex)))

	hash := sha256.Sum256(effectiveConfig)
	actualSHA256Hex := hex.EncodeToString(hash[:])

	// Compare
	if actualSHA256Hex != string(expectedSHA256Hex) {
		return fmt.Errorf("sha256 mismatch: config file has been modified (expected %s, got %s)",
			string(expectedSHA256Hex), actualSHA256Hex)
	}

	return nil
}
