package main

import (
	"context"
	"database/sql"
	_ "embed"
	"encoding/json"
	"fmt"
	"html/template"
	"net"
	"net/http"
	"sort"
	"strings"
	"time"
)

//go:embed dashboard.html
var dashboardHTML string

type dbProvider interface {
	DB() *sql.DB
}

type dashboardSnapshot struct {
	GeneratedAt  string                 `json:"generated_at"`
	Version      string                 `json:"version"`
	Mode         string                 `json:"mode"`
	Commit       string                 `json:"commit"`
	Counts       dashboardCounts        `json:"counts"`
	LatestTick   dashboardTick          `json:"latest_tick"`
	Pools        []dashboardPool        `json:"pools"`
	Positions    []dashboardPosition    `json:"positions"`
	Transactions []dashboardTransaction `json:"transactions"`
	RecentScores []dashboardScore       `json:"recent_scores"`
	Warnings     []string               `json:"warnings"`
}

type dashboardCounts struct {
	Pools        int64 `json:"pools"`
	Scores       int64 `json:"scores"`
	Positions    int64 `json:"positions"`
	Transactions int64 `json:"transactions"`
}

type dashboardTick struct {
	UpdatedAt       int64  `json:"updated_at"`
	UpdatedAtText   string `json:"updated_at_text"`
	ScannedEstimate int64  `json:"scanned_estimate"`
}

type dashboardPool struct {
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	Protocol  string `json:"protocol"`
	Token0    string `json:"token0"`
	Token1    string `json:"token1"`
	FeeBPS    int    `json:"fee_bps"`
	Tier      string `json:"tier"`
	Score     string `json:"score"`
	UpdatedAt int64  `json:"updated_at"`
}

type dashboardPosition struct {
	ID        string `json:"id"`
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	Status    string `json:"status"`
	Tier      string `json:"tier"`
	AmountUSD string `json:"amount_usd"`
	OpenedAt  int64  `json:"opened_at"`
	ClosedAt  int64  `json:"closed_at"`
}

type dashboardTransaction struct {
	ID        string `json:"id"`
	Chain     string `json:"chain"`
	TxHash    string `json:"tx_hash"`
	Status    string `json:"status"`
	CreatedAt int64  `json:"created_at"`
	UpdatedAt int64  `json:"updated_at"`
}

type dashboardScore struct {
	PoolID    string `json:"pool_id"`
	Chain     int    `json:"chain"`
	BlockTime int64  `json:"block_time"`
	ScoreJSON string `json:"score_json"`
}

func (app *App) registerDashboardRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/", app.dashboardAuth(app.handleDashboard))
	mux.HandleFunc("/dashboard", app.dashboardAuth(app.handleDashboard))
	mux.HandleFunc("/api/dashboard", app.dashboardAuth(app.handleDashboardAPI))
}

func (app *App) dashboardAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token := ""
		if app.config != nil {
			token = strings.TrimSpace(app.config.Platform.DashboardToken)
		}
		if token == "" || requestFromLoopback(r) || dashboardTokenMatches(r, token) {
			next(w, r)
			return
		}
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}
}

func requestFromLoopback(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func dashboardTokenMatches(r *http.Request, token string) bool {
	if r.URL.Query().Get("token") == token {
		return true
	}
	auth := r.Header.Get("Authorization")
	return strings.TrimPrefix(auth, "Bearer ") == token
}

func (app *App) handleDashboard(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	tmpl := template.Must(template.New("dashboard").Parse(dashboardHTML))
	_ = tmpl.Execute(w, map[string]string{
		"Version": Version,
		"Mode":    BuildMode,
		"Commit":  BuildCommit,
	})
}

func (app *App) handleDashboardAPI(w http.ResponseWriter, r *http.Request) {
	snapshot, err := app.dashboardSnapshot(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(snapshot)
}

func (app *App) dashboardSnapshot(ctx context.Context) (dashboardSnapshot, error) {
	snapshot := dashboardSnapshot{
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
		Version:     Version,
		Mode:        BuildMode,
		Commit:      BuildCommit,
	}
	provider, ok := app.store.(dbProvider)
	if !ok || provider.DB() == nil {
		snapshot.Warnings = append(snapshot.Warnings, "dashboard requires postgres store with DB access")
		return snapshot, nil
	}
	db := provider.DB()
	if err := db.QueryRowContext(ctx, `
		SELECT
			(SELECT count(*) FROM pools),
			(SELECT count(*) FROM pool_score_history),
			(SELECT count(*) FROM positions),
			(SELECT count(*) FROM transactions)
	`).Scan(&snapshot.Counts.Pools, &snapshot.Counts.Scores, &snapshot.Counts.Positions, &snapshot.Counts.Transactions); err != nil {
		return snapshot, fmt.Errorf("query dashboard counts: %w", err)
	}

	_ = db.QueryRowContext(ctx, `
		SELECT COALESCE(max(block_time), 0), count(DISTINCT pool_id)
		FROM pool_score_history
		WHERE block_time = (SELECT max(block_time) FROM pool_score_history)
	`).Scan(&snapshot.LatestTick.UpdatedAt, &snapshot.LatestTick.ScannedEstimate)
	if snapshot.LatestTick.UpdatedAt > 0 {
		snapshot.LatestTick.UpdatedAtText = time.Unix(snapshot.LatestTick.UpdatedAt, 0).UTC().Format(time.RFC3339)
	}

	pools, err := queryDashboardPools(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Pools = pools

	positions, err := queryDashboardPositions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Positions = positions

	txs, err := queryDashboardTransactions(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.Transactions = txs

	scores, err := queryDashboardScores(ctx, db)
	if err != nil {
		return snapshot, err
	}
	snapshot.RecentScores = scores

	return snapshot, nil
}

func queryDashboardPools(ctx context.Context, db *sql.DB) ([]dashboardPool, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT pool_id, chain, protocol, token0, token1, fee_bps,
		       COALESCE(tier, ''), COALESCE(last_score, ''), updated_at
		FROM pools
		ORDER BY updated_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard pools: %w", err)
	}
	defer rows.Close()

	var pools []dashboardPool
	for rows.Next() {
		var pool dashboardPool
		if err := rows.Scan(&pool.PoolID, &pool.Chain, &pool.Protocol, &pool.Token0, &pool.Token1, &pool.FeeBPS, &pool.Tier, &pool.Score, &pool.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard pool: %w", err)
		}
		pools = append(pools, pool)
	}
	return pools, rows.Err()
}

func queryDashboardPositions(ctx context.Context, db *sql.DB) ([]dashboardPosition, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, pool_id, chain, status, COALESCE(tier, ''), amount_usd, opened_at, COALESCE(closed_at, 0)
		FROM positions
		ORDER BY opened_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard positions: %w", err)
	}
	defer rows.Close()

	var positions []dashboardPosition
	for rows.Next() {
		var pos dashboardPosition
		if err := rows.Scan(&pos.ID, &pos.PoolID, &pos.Chain, &pos.Status, &pos.Tier, &pos.AmountUSD, &pos.OpenedAt, &pos.ClosedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard position: %w", err)
		}
		positions = append(positions, pos)
	}
	return positions, rows.Err()
}

func queryDashboardTransactions(ctx context.Context, db *sql.DB) ([]dashboardTransaction, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT id, chain, tx_hash, status, created_at, updated_at
		FROM transactions
		ORDER BY created_at DESC
		LIMIT 50
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard transactions: %w", err)
	}
	defer rows.Close()

	var txs []dashboardTransaction
	for rows.Next() {
		var tx dashboardTransaction
		if err := rows.Scan(&tx.ID, &tx.Chain, &tx.TxHash, &tx.Status, &tx.CreatedAt, &tx.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan dashboard transaction: %w", err)
		}
		txs = append(txs, tx)
	}
	return txs, rows.Err()
}

func queryDashboardScores(ctx context.Context, db *sql.DB) ([]dashboardScore, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT pool_id, chain, block_time, score_json
		FROM pool_score_history
		ORDER BY id DESC
		LIMIT 20
	`)
	if err != nil {
		return nil, fmt.Errorf("query dashboard scores: %w", err)
	}
	defer rows.Close()

	var scores []dashboardScore
	for rows.Next() {
		var score dashboardScore
		if err := rows.Scan(&score.PoolID, &score.Chain, &score.BlockTime, &score.ScoreJSON); err != nil {
			return nil, fmt.Errorf("scan dashboard score: %w", err)
		}
		scores = append(scores, score)
	}
	sort.Slice(scores, func(i, j int) bool {
		return scores[i].BlockTime > scores[j].BlockTime
	})
	return scores, rows.Err()
}
