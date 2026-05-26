package main

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/sqlite"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
)

func TestClassifyShadowOutcomeLabel(t *testing.T) {
	for _, tc := range []struct {
		name       string
		selected   bool
		intentOpen bool
		action     string
		valid      bool
		netPnLUSD  string
		want       string
	}{
		{
			name:       "not selected is skip",
			selected:   false,
			intentOpen: false,
			action:     "skip",
			valid:      true,
			netPnLUSD:  "0",
			want:       "skip",
		},
		{
			name:       "selected without usable data is invalid",
			selected:   true,
			intentOpen: true,
			action:     "open_shadow_position",
			valid:      false,
			netPnLUSD:  "0",
			want:       "invalid",
		},
		{
			name:       "positive net pnl is win",
			selected:   true,
			intentOpen: true,
			action:     "open_shadow_position",
			valid:      true,
			netPnLUSD:  "1.25",
			want:       "win",
		},
		{
			name:       "negative net pnl is loss",
			selected:   true,
			intentOpen: true,
			action:     "reuse_shadow_position",
			valid:      true,
			netPnLUSD:  "-0.10",
			want:       "loss",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := classifyShadowOutcomeLabel(tc.selected, tc.intentOpen, tc.action, tc.valid, decimalFromStringSafe(tc.netPnLUSD))
			require.Equal(t, tc.want, got)
		})
	}
}

func TestBackfillShadowOutcomes_WritesOutcomeIdempotently(t *testing.T) {
	store, err := sqlite.NewStore(filepath.Join(t.TempDir(), "shadow_outcomes.sqlite"))
	require.NoError(t, err)

	db := store.DB()
	_, err = db.Exec(`
		CREATE TABLE shadow_decision_trace (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			tick_time BIGINT NOT NULL,
			trace_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			pool_key TEXT NOT NULL,
			chain TEXT NOT NULL,
			protocol TEXT NOT NULL,
			score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
			score_json TEXT NOT NULL,
			selected BOOLEAN NOT NULL DEFAULT FALSE,
			selected_rank INTEGER,
			selection_reason TEXT NOT NULL DEFAULT '',
			intent_open BOOLEAN NOT NULL DEFAULT FALSE,
			intent_reason TEXT NOT NULL DEFAULT '',
			chain_stage TEXT NOT NULL DEFAULT '',
			chain_reason TEXT NOT NULL DEFAULT '',
			pipeline_stage TEXT NOT NULL DEFAULT '',
			pipeline_ok BOOLEAN NOT NULL DEFAULT FALSE,
			pipeline_reason TEXT NOT NULL DEFAULT '',
			final_action TEXT NOT NULL DEFAULT 'skip',
			position_id TEXT,
			tx_hash TEXT,
			created_at BIGINT NOT NULL
		)
	`)
	require.NoError(t, err)
	_, err = db.Exec(`
		CREATE TABLE shadow_position_marks (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			mark_time BIGINT NOT NULL,
			position_id TEXT NOT NULL,
			pool_id TEXT NOT NULL,
			chain TEXT NOT NULL,
			status TEXT NOT NULL,
			tier TEXT NOT NULL DEFAULT '',
			amount_usd TEXT NOT NULL DEFAULT '0',
			source TEXT NOT NULL DEFAULT '',
			hold_minutes BIGINT NOT NULL DEFAULT 0,
			valuation_usd TEXT NOT NULL DEFAULT '0',
			fee_usd TEXT NOT NULL DEFAULT '0',
			il_usd TEXT NOT NULL DEFAULT '0',
			net_pnl_usd TEXT NOT NULL DEFAULT '0',
			current_tvl_usd TEXT NOT NULL DEFAULT '0',
			current_vol24h_usd TEXT NOT NULL DEFAULT '0',
			price_change_pct TEXT NOT NULL DEFAULT '0',
			created_at BIGINT NOT NULL
		)
	`)
	require.NoError(t, err)
	_, err = db.Exec(`
		CREATE TABLE pools (
			pool_id TEXT NOT NULL,
			chain INTEGER NOT NULL,
			protocol TEXT NOT NULL,
			token0 TEXT NOT NULL,
			token1 TEXT NOT NULL,
			fee_bps INTEGER NOT NULL,
			tier TEXT,
			audit_verdict TEXT,
			last_score TEXT,
			updated_block INTEGER,
			updated_at BIGINT NOT NULL,
			liquidity TEXT,
			tick BIGINT,
			tvl_usd TEXT,
			vol_24h TEXT,
			fee_apr_24h TEXT
		)
	`)
	require.NoError(t, err)

	now := time.Now().UTC()
	decisionTime := now.Add(-2 * time.Hour).Unix()
	_, err = db.Exec(`
		INSERT INTO shadow_decision_trace (
			tick_time, trace_id, pool_id, pool_key, chain, protocol, score_total, score_json,
			selected, selected_rank, selection_reason, intent_open, intent_reason,
			chain_stage, chain_reason, pipeline_stage, pipeline_ok, pipeline_reason,
			final_action, position_id, tx_hash, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, decisionTime, "trace-1", "pool-1", "base:uni:pool-1", "base", "uniswap_v3", 82.0, `{"VolatilityScore":72}`,
		true, 1, "selected", true, "open", "chain_v3_validated", "", "order_opened", true, "ok",
		"open_shadow_position", "pos-1", "tx-1", decisionTime*1000)
	require.NoError(t, err)
	_, err = db.Exec(`
		INSERT INTO shadow_position_marks (
			mark_time, position_id, pool_id, chain, status, tier, amount_usd, source,
			hold_minutes, valuation_usd, fee_usd, il_usd, net_pnl_usd, current_tvl_usd, current_vol24h_usd, price_change_pct, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, now.Add(-30*time.Minute).Unix(), "pos-1", "pool-1", "base", "open", "A", "10", "onchain_value",
		90, "11.2", "0.7", "-0.2", "1.5", "250000", "180000", "0.03", now.UnixMilli())
	require.NoError(t, err)
	_, err = db.Exec(`
		INSERT INTO pools (
			pool_id, chain, protocol, token0, token1, fee_bps, updated_at, tvl_usd, vol_24h
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "pool-1", 8453, "uniswap_v3", baseUSDCAddress, baseWETHAddress, 30, now.UnixMilli(), "250000", "180000")
	require.NoError(t, err)

	app := &App{
		logger: zap.NewNop(),
		config: &config.Config{
			Store: config.Store{Backend: "sqlite", SQLitePath: filepath.Join(t.TempDir(), "unused.sqlite")},
		},
		store: store,
	}
	require.NoError(t, app.ensureShadowOutcomeLabelsTable(context.Background()))
	require.NoError(t, app.backfillShadowOutcomes(context.Background(), now, "1h"))
	require.NoError(t, app.backfillShadowOutcomes(context.Background(), now, "1h"))

	var count int
	var label, horizon, netPnL string
	err = db.QueryRow(`
		SELECT COUNT(*), MAX(label), MAX(horizon), MAX(simulated_net_pnl_usd)
		FROM shadow_outcome_labels
	`).Scan(&count, &label, &horizon, &netPnL)
	require.NoError(t, err)
	require.Equal(t, 1, count)
	require.Equal(t, "win", label)
	require.Equal(t, "1h", horizon)
	require.Equal(t, "1.5", netPnL)
}

func TestResolveShadowOutcomeHorizons(t *testing.T) {
	all, err := resolveShadowOutcomeHorizons("")
	require.NoError(t, err)
	require.Len(t, all, 3)

	only6h, err := resolveShadowOutcomeHorizons("6h")
	require.NoError(t, err)
	require.Len(t, only6h, 1)
	require.Equal(t, "6h", only6h[0].Name)

	_, err = resolveShadowOutcomeHorizons("2h")
	require.Error(t, err)
}

func TestRenderShadowOutcomeReport(t *testing.T) {
	report := renderShadowOutcomeReport([]shadowOutcomeReportRow{
		{
			Horizon:         "1h",
			Label:           "win",
			Selected:        true,
			ScoreTotal:      82,
			SimulatedNetPnL: decimalFromStringSafe("1.25"),
			MaxDrawdownUSD:  decimalFromStringSafe("-0.40"),
			FeeTierBPS:      30,
			TVLUSD:          decimalFromStringSafe("250000"),
			VolatilityScore: 72,
		},
		{
			Horizon:         "1h",
			Label:           "loss",
			Selected:        true,
			ScoreTotal:      65,
			SimulatedNetPnL: decimalFromStringSafe("-0.20"),
			MaxDrawdownUSD:  decimalFromStringSafe("-0.80"),
			FeeTierBPS:      100,
			TVLUSD:          decimalFromStringSafe("90000"),
			VolatilityScore: 45,
		},
	}, time.Unix(1_700_000_000, 0).UTC())

	require.True(t, strings.Contains(report, "Shadow Outcome 回填报告"))
	require.True(t, strings.Contains(report, "## 1h"))
	require.True(t, strings.Contains(report, "按 Score Bucket"))
	require.True(t, strings.Contains(report, "30 bps"))
	require.True(t, strings.Contains(report, "invalid_rate"))
	require.True(t, strings.Contains(report, "high_score_vs_low_score"))
}

func TestClassifyShadowOutcomeVerdict_SampleInsufficientIsWarn(t *testing.T) {
	stats := shadowOutcomeReportStats{
		RealizedSampleCount: 5,
		AvgNetPnL:           decimalFromStringSafe("0.25"),
		MedianNetPnL:        decimalFromStringSafe("0.20"),
		P10ThresholdUSD:     decimalFromStringSafe("-1.0"),
		HighScoreVsLow:      "better",
	}
	require.Equal(t, "WARN", classifyShadowOutcomeVerdict(stats))
}

func TestClassifyShadowOutcomeVerdict_RejectsHighInvalidRate(t *testing.T) {
	stats := shadowOutcomeReportStats{
		RealizedSampleCount: 25,
		InvalidRate:         0.35,
		AvgNetPnL:           decimalFromStringSafe("0.25"),
		MedianNetPnL:        decimalFromStringSafe("0.10"),
		P10NetPnL:           decimalFromStringSafe("-0.50"),
		P10ThresholdUSD:     decimalFromStringSafe("-1.0"),
		HighScoreVsLow:      "better",
	}
	require.Equal(t, "FAIL", classifyShadowOutcomeVerdict(stats))
}
