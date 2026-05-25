package main

import (
	"context"
	"database/sql"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strings"
	"time"

	solanago "github.com/gagliardetto/solana-go"
	solrpc "github.com/gagliardetto/solana-go/rpc"
	"github.com/lpbot/lpbot/internal/adapters/datasource/dexscreener"
	"github.com/lpbot/lpbot/internal/adapters/datasource/geckoterminal"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

type solanaLPRangeSummary struct {
	CurrentTick        int32
	TickLower          int32
	TickUpper          int32
	CurrentPrice       domain.Decimal
	LowerPrice         domain.Decimal
	UpperPrice         domain.Decimal
	WidthBPS           domain.Decimal
	DistanceLowerBPS   domain.Decimal
	DistanceUpperBPS   domain.Decimal
	BoundaryWarningBPS domain.Decimal
	OccupancyFactor    domain.Decimal
	InRange            bool
}

type solanaLPFeeProjection struct {
	FeeBPS            uint
	PoolTVLUSD        domain.Decimal
	PoolVol24hUSD     domain.Decimal
	PositionValueUSD  domain.Decimal
	EstimatedSharePct domain.Decimal
	EstimatedFee24hUSD domain.Decimal
	EstimatedAPR      domain.Decimal
}

type solanaLPExitSignal struct {
	Action               string
	Reason               string
	NearBoundary         bool
	OutOfRange           bool
	ExpectedCloseCostUSD domain.Decimal
	ExpectedNetEdge24hUSD domain.Decimal
}

type solanaLPPositionMetadata struct {
	Protocol             string `json:"protocol"`
	PoolID               string `json:"pool_id"`
	PositionNFTMint      string `json:"position_nft_mint"`
	OpenTxHash           string `json:"open_tx_hash"`
	PositionLiquidityRaw string `json:"position_liquidity_raw"`
	TokenFeesOwed0Raw    uint64 `json:"token_fees_owed_0_raw"`
	TokenFeesOwed1Raw    uint64 `json:"token_fees_owed_1_raw"`
	RewardAmountsOwedRaw []uint64 `json:"reward_amounts_owed_raw"`
	Token0Mint           string `json:"token0_mint"`
	Token1Mint           string `json:"token1_mint"`
	Token0MaxRaw         uint64 `json:"token0_max_raw"`
	Token1MaxRaw         uint64 `json:"token1_max_raw"`
	TargetTotalUSD       string `json:"target_total_usd"`
	CurrentTick          int32  `json:"current_tick"`
	TickLower            int32  `json:"tick_lower"`
	TickUpper            int32  `json:"tick_upper"`
	CurrentPrice         string `json:"current_price"`
	LowerPrice           string `json:"lower_price"`
	UpperPrice           string `json:"upper_price"`
	WidthBPS             string `json:"width_bps"`
	DistanceLowerBPS     string `json:"distance_lower_bps"`
	DistanceUpperBPS     string `json:"distance_upper_bps"`
	BoundaryWarningBPS   string `json:"boundary_warning_bps"`
	OccupancyFactor      string `json:"occupancy_factor"`
	InRange              bool   `json:"in_range"`
	FeeBPS               uint   `json:"fee_bps"`
	PoolTVLUSD           string `json:"pool_tvl_usd"`
	PoolVol24hUSD        string `json:"pool_vol24h_usd"`
	EstimatedSharePct    string `json:"estimated_share_pct"`
	EstimatedFee24hUSD   string `json:"estimated_fee_24h_usd"`
	EstimatedAPR         string `json:"estimated_apr"`
	ExitAction           string `json:"exit_action"`
	ExitReason           string `json:"exit_reason"`
	ExpectedCloseCostUSD string `json:"expected_close_cost_usd"`
	ExpectedNetEdge24hUSD string `json:"expected_net_edge_24h_usd"`
}

type solanaLPClosePreflight struct {
	PoolID      string
	Protocol    string
	Position    *domain.Position
	Metadata    solanaLPPositionMetadata
	Blocker     string
	CloseCandidate bool
	DecreaseBuildReady bool
	DecreaseSignReady bool
	DecreaseSimReady bool
	DecreaseBlocker string
	CollectBuildReady bool
	CollectSignReady bool
	CollectSimReady bool
	CollectBlocker string
	CloseBuildReady bool
	CloseSignReady bool
	CloseSimReady bool
	CloseBlocker string
	FullExitPathReady bool
	CloseTxBase64Len int
	CloseSignature string
	CloseSimUnits uint64
	CloseSimErr string
}

func buildSolanaLPRangeSummary(state pancakeswapSolanaPoolState, tickLower int32, tickUpper int32) solanaLPRangeSummary {
	currentPrice := decimalFromFloat(pancakeSqrtPriceX64ToPrice(state.SqrtPriceX64, int(state.MintDecimals0)-int(state.MintDecimals1)))
	lowerPrice := decimalFromFloat(pancakeTickToPrice(int(tickLower), int(state.MintDecimals0)-int(state.MintDecimals1)))
	upperPrice := decimalFromFloat(pancakeTickToPrice(int(tickUpper), int(state.MintDecimals0)-int(state.MintDecimals1)))
	inRange := state.CurrentTick > tickLower && state.CurrentTick < tickUpper && currentPrice.GreaterThan(lowerPrice) && currentPrice.LessThan(upperPrice)

	widthBPS := domain.ZeroDecimal()
	distLower := domain.ZeroDecimal()
	distUpper := domain.ZeroDecimal()
	occupancy := domain.ZeroDecimal()
	if !currentPrice.IsZero() {
		widthBPS = upperPrice.Sub(lowerPrice).Div(currentPrice).Mul(domain.MustDecimal("10000"))
		distLower = currentPrice.Sub(lowerPrice).Div(currentPrice).Mul(domain.MustDecimal("10000"))
		distUpper = upperPrice.Sub(currentPrice).Div(currentPrice).Mul(domain.MustDecimal("10000"))
	}
	if inRange {
		totalDist := distLower.Add(distUpper)
		if !totalDist.IsZero() {
			minDist := solanaMinDecimal(distLower, distUpper)
			occupancy = minDist.Mul(domain.MustDecimal("2")).Div(totalDist)
		}
	}
	boundaryWarning := solanaMaxDecimal(domain.MustDecimal("50"), widthBPS.Div(domain.MustDecimal("6")))
	return solanaLPRangeSummary{
		CurrentTick:        state.CurrentTick,
		TickLower:          tickLower,
		TickUpper:          tickUpper,
		CurrentPrice:       currentPrice,
		LowerPrice:         lowerPrice,
		UpperPrice:         upperPrice,
		WidthBPS:           widthBPS,
		DistanceLowerBPS:   distLower,
		DistanceUpperBPS:   distUpper,
		BoundaryWarningBPS: boundaryWarning,
		OccupancyFactor:    occupancy,
		InRange:            inRange,
	}
}

func estimateSolanaLPFeeProjection(positionValueUSD domain.Decimal, feeBPS uint, poolTVLUSD, poolVol24hUSD domain.Decimal, rangeSummary solanaLPRangeSummary) solanaLPFeeProjection {
	if positionValueUSD.LessThanOrEqual(domain.ZeroDecimal()) || poolTVLUSD.LessThanOrEqual(domain.ZeroDecimal()) || poolVol24hUSD.LessThanOrEqual(domain.ZeroDecimal()) || feeBPS == 0 {
		return solanaLPFeeProjection{
			FeeBPS:           feeBPS,
			PoolTVLUSD:       poolTVLUSD,
			PoolVol24hUSD:    poolVol24hUSD,
			PositionValueUSD: positionValueUSD,
		}
	}
	shareRatio := positionValueUSD.Div(poolTVLUSD)
	sharePct := shareRatio.Mul(domain.MustDecimal("100"))
	feeRate := domain.NewDecimalFromInt(int64(feeBPS)).Div(domain.MustDecimal("10000"))
	fee24h := poolVol24hUSD.Mul(feeRate).Mul(shareRatio).Mul(rangeSummary.OccupancyFactor)
	apr := domain.ZeroDecimal()
	if positionValueUSD.GreaterThan(domain.ZeroDecimal()) {
		apr = fee24h.Mul(domain.MustDecimal("365")).Div(positionValueUSD).Mul(domain.MustDecimal("100"))
	}
	return solanaLPFeeProjection{
		FeeBPS:             feeBPS,
		PoolTVLUSD:         poolTVLUSD,
		PoolVol24hUSD:      poolVol24hUSD,
		PositionValueUSD:   positionValueUSD,
		EstimatedSharePct:  sharePct,
		EstimatedFee24hUSD: fee24h,
		EstimatedAPR:       apr,
	}
}

func deriveSolanaLPExitSignal(rangeSummary solanaLPRangeSummary, projection solanaLPFeeProjection, closeCostUSD domain.Decimal) solanaLPExitSignal {
	minBoundaryDist := solanaMinDecimal(rangeSummary.DistanceLowerBPS, rangeSummary.DistanceUpperBPS)
	nearBoundary := rangeSummary.InRange && minBoundaryDist.LessThanOrEqual(rangeSummary.BoundaryWarningBPS)
	outOfRange := !rangeSummary.InRange
	netEdge := projection.EstimatedFee24hUSD.Sub(closeCostUSD)
	switch {
	case outOfRange:
		return solanaLPExitSignal{
			Action:                "exit_now",
			Reason:                "out_of_range",
			NearBoundary:          false,
			OutOfRange:            true,
			ExpectedCloseCostUSD:  closeCostUSD,
			ExpectedNetEdge24hUSD: netEdge,
		}
	case nearBoundary && netEdge.LessThanOrEqual(domain.ZeroDecimal()):
		return solanaLPExitSignal{
			Action:                "exit_now",
			Reason:                "near_boundary_negative_edge",
			NearBoundary:          true,
			OutOfRange:            false,
			ExpectedCloseCostUSD:  closeCostUSD,
			ExpectedNetEdge24hUSD: netEdge,
		}
	case nearBoundary:
		return solanaLPExitSignal{
			Action:                "watch_boundary",
			Reason:                "near_boundary_positive_edge",
			NearBoundary:          true,
			OutOfRange:            false,
			ExpectedCloseCostUSD:  closeCostUSD,
			ExpectedNetEdge24hUSD: netEdge,
		}
	default:
		return solanaLPExitSignal{
			Action:                "hold",
			Reason:                "in_range_positive_edge",
			NearBoundary:          false,
			OutOfRange:            false,
			ExpectedCloseCostUSD:  closeCostUSD,
			ExpectedNetEdge24hUSD: netEdge,
		}
	}
}

func computeSolanaLPAnalytics(ctx context.Context, poolID string, protocol string, poolMeta *ports.PoolDiscovery, state pancakeswapSolanaPoolState, tickLower int32, tickUpper int32, positionValueUSD domain.Decimal, maxPriorityLamports uint64) (solanaLPRangeSummary, solanaLPFeeProjection, solanaLPExitSignal) {
	rangeSummary := buildSolanaLPRangeSummary(state, tickLower, tickUpper)
	if poolMeta == nil {
		poolMeta = lookupSolanaPoolDiscovery(ctx, poolID, protocol)
	}
	feeBPS := poolMeta.FeeBPS
	if feeBPS == 0 && state.TradeFeeBPS > 0 {
		feeBPS = state.TradeFeeBPS
	}
	feeProjection := estimateSolanaLPFeeProjection(positionValueUSD, feeBPS, poolMeta.TVLUSD, poolMeta.Vol24h, rangeSummary)
	closeCostUSD := estimateSolanaLPCloseCostUSD(rangeSummary.CurrentPrice, maxPriorityLamports)
	exitSignal := deriveSolanaLPExitSignal(rangeSummary, feeProjection, closeCostUSD)
	return rangeSummary, feeProjection, exitSignal
}

func buildSolanaLPPositionMetadata(protocol string, poolID string, build pancakeswapSolanaOpenPositionBuild, plan solanaLPFundingPlan, txHash string, rangeSummary solanaLPRangeSummary, feeProjection solanaLPFeeProjection, exitSignal solanaLPExitSignal) (string, error) {
	raw, err := json.Marshal(solanaLPPositionMetadata{
		Protocol:              protocol,
		PoolID:                poolID,
		PositionNFTMint:       build.PositionNFT.PublicKey().String(),
		OpenTxHash:            txHash,
		PositionLiquidityRaw:  "0",
		TokenFeesOwed0Raw:     0,
		TokenFeesOwed1Raw:     0,
		RewardAmountsOwedRaw:  nil,
		Token0Mint:            build.PoolState.TokenMint0.String(),
		Token1Mint:            build.PoolState.TokenMint1.String(),
		Token0MaxRaw:          build.Amount0Max,
		Token1MaxRaw:          build.Amount1Max,
		TargetTotalUSD:        plan.TargetTotalUSD.String(),
		CurrentTick:           rangeSummary.CurrentTick,
		TickLower:             rangeSummary.TickLower,
		TickUpper:             rangeSummary.TickUpper,
		CurrentPrice:          rangeSummary.CurrentPrice.String(),
		LowerPrice:            rangeSummary.LowerPrice.String(),
		UpperPrice:            rangeSummary.UpperPrice.String(),
		WidthBPS:              rangeSummary.WidthBPS.String(),
		DistanceLowerBPS:      rangeSummary.DistanceLowerBPS.String(),
		DistanceUpperBPS:      rangeSummary.DistanceUpperBPS.String(),
		BoundaryWarningBPS:    rangeSummary.BoundaryWarningBPS.String(),
		OccupancyFactor:       rangeSummary.OccupancyFactor.String(),
		InRange:               rangeSummary.InRange,
		FeeBPS:                feeProjection.FeeBPS,
		PoolTVLUSD:            feeProjection.PoolTVLUSD.String(),
		PoolVol24hUSD:         feeProjection.PoolVol24hUSD.String(),
		EstimatedSharePct:     feeProjection.EstimatedSharePct.String(),
		EstimatedFee24hUSD:    feeProjection.EstimatedFee24hUSD.String(),
		EstimatedAPR:          feeProjection.EstimatedAPR.String(),
		ExitAction:            exitSignal.Action,
		ExitReason:            exitSignal.Reason,
		ExpectedCloseCostUSD:  exitSignal.ExpectedCloseCostUSD.String(),
		ExpectedNetEdge24hUSD: exitSignal.ExpectedNetEdge24hUSD.String(),
	})
	if err != nil {
		return "", fmt.Errorf("marshal solana lp position metadata: %w", err)
	}
	return string(raw), nil
}

func saveConfirmedSolanaOpenPosition(ctx context.Context, db *sql.DB, poolID string, protocol string, build pancakeswapSolanaOpenPositionBuild, plan solanaLPFundingPlan, txHash string, metadataJSON string) error {
	if db == nil {
		return fmt.Errorf("position store db is nil")
	}
	positionID := build.PositionNFT.PublicKey().String()
	pos := &domain.Position{
		ID:           positionID,
		TokenID:      positionID,
		PoolID:       poolID,
		Chain:        domain.ChainSolana,
		Protocol:     protocol,
		Status:       domain.StatusOpen,
		AmountUSD:    plan.TargetTotalUSD,
		OpenTxHash:   txHash,
		MetadataJSON: metadataJSON,
		TickLower:    int64(build.TickLower),
		TickUpper:    int64(build.TickUpper),
		OpenedAt:     time.Now().Unix(),
	}
	return postgres.NewPositionRepo(db).Save(ctx, pos)
}

type reconciledSolanaOpenPosition struct {
	PositionID string
	PoolID     string
	Protocol   string
	TickLower  int32
	TickUpper  int32
	Amount0Max uint64
	Amount1Max uint64
	BaseFlag   bool
	TxHash     string
}

func maybeBackfillLatestSolanaOpenCanaryPosition(ctx context.Context, cfg *config.Config, maxPriorityLamports uint64) error {
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		return nil
	}
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return err
	}
	defer store.Close()

	db := store.DB()
	txHash, err := latestSolanaOpenCanaryBroadcastTxHash(ctx, db)
	if err != nil || strings.TrimSpace(txHash) == "" {
		return err
	}
	exists, err := solanaOpenPositionExists(ctx, db, txHash)
	if err != nil || exists {
		return err
	}
	reconciled, err := decodeSolanaOpenPositionFromStoredTx(ctx, db, txHash)
	if err != nil {
		return err
	}
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	poolPubkey, err := solanago.PublicKeyFromBase58(reconciled.PoolID)
	if err != nil {
		return err
	}
	poolState, err := fetchPancakeSolanaPoolState(ctx, client, poolPubkey)
	if err != nil {
		return err
	}
	rangeSummary, feeProjection, exitSignal := computeSolanaLPAnalytics(ctx, reconciled.PoolID, reconciled.Protocol, nil, poolState, reconciled.TickLower, reconciled.TickUpper, domain.MustDecimal("10"), maxPriorityLamports)
	meta, err := json.Marshal(solanaLPPositionMetadata{
		Protocol:              reconciled.Protocol,
		PoolID:                reconciled.PoolID,
		PositionNFTMint:       reconciled.PositionID,
		OpenTxHash:            reconciled.TxHash,
		PositionLiquidityRaw:  "0",
		TokenFeesOwed0Raw:     0,
		TokenFeesOwed1Raw:     0,
		RewardAmountsOwedRaw:  nil,
		Token0Mint:            poolState.TokenMint0.String(),
		Token1Mint:            poolState.TokenMint1.String(),
		Token0MaxRaw:          reconciled.Amount0Max,
		Token1MaxRaw:          reconciled.Amount1Max,
		TargetTotalUSD:        "10",
		CurrentTick:           rangeSummary.CurrentTick,
		TickLower:             reconciled.TickLower,
		TickUpper:             reconciled.TickUpper,
		CurrentPrice:          rangeSummary.CurrentPrice.String(),
		LowerPrice:            rangeSummary.LowerPrice.String(),
		UpperPrice:            rangeSummary.UpperPrice.String(),
		WidthBPS:              rangeSummary.WidthBPS.String(),
		DistanceLowerBPS:      rangeSummary.DistanceLowerBPS.String(),
		DistanceUpperBPS:      rangeSummary.DistanceUpperBPS.String(),
		BoundaryWarningBPS:    rangeSummary.BoundaryWarningBPS.String(),
		OccupancyFactor:       rangeSummary.OccupancyFactor.String(),
		InRange:               rangeSummary.InRange,
		FeeBPS:                feeProjection.FeeBPS,
		PoolTVLUSD:            feeProjection.PoolTVLUSD.String(),
		PoolVol24hUSD:         feeProjection.PoolVol24hUSD.String(),
		EstimatedSharePct:     feeProjection.EstimatedSharePct.String(),
		EstimatedFee24hUSD:    feeProjection.EstimatedFee24hUSD.String(),
		EstimatedAPR:          feeProjection.EstimatedAPR.String(),
		ExitAction:            exitSignal.Action,
		ExitReason:            exitSignal.Reason,
		ExpectedCloseCostUSD:  exitSignal.ExpectedCloseCostUSD.String(),
		ExpectedNetEdge24hUSD: exitSignal.ExpectedNetEdge24hUSD.String(),
	})
	if err != nil {
		return err
	}
	pos := &domain.Position{
		ID:           reconciled.PositionID,
		TokenID:      reconciled.PositionID,
		PoolID:       reconciled.PoolID,
		Chain:        domain.ChainSolana,
		Protocol:     reconciled.Protocol,
		Status:       domain.StatusOpen,
		AmountUSD:    domain.MustDecimal("10"),
		OpenTxHash:   reconciled.TxHash,
		MetadataJSON: string(meta),
		TickLower:    int64(reconciled.TickLower),
		TickUpper:    int64(reconciled.TickUpper),
		OpenedAt:     time.Now().Unix(),
	}
	return postgres.NewPositionRepo(db).Save(ctx, pos)
}

func latestSolanaOpenCanaryBroadcastTxHash(ctx context.Context, db *sql.DB) (string, error) {
	if db == nil {
		return "", nil
	}
	var txHash string
	err := db.QueryRowContext(ctx, `
		SELECT tx_hash
		FROM canary_events
		WHERE chain = 'solana'
		  AND command = 'solana_lp_open_canary'
		  AND stage = 'broadcast'
		  AND status = 'ok'
		ORDER BY created_at DESC
		LIMIT 1
	`).Scan(&txHash)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("query latest solana open canary broadcast: %w", err)
	}
	return strings.TrimSpace(txHash), nil
}

func solanaOpenPositionExists(ctx context.Context, db *sql.DB, txHash string) (bool, error) {
	if db == nil || strings.TrimSpace(txHash) == "" {
		return false, nil
	}
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1
			FROM positions
			WHERE chain = 2
			  AND status IN ('open','opening')
			  AND open_tx_hash = $1
		)
	`, txHash).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("check existing solana open position: %w", err)
	}
	return exists, nil
}

func findExistingOpenSolanaPositionForPool(ctx context.Context, db *sql.DB, poolID string) (*domain.Position, error) {
	if db == nil || strings.TrimSpace(poolID) == "" {
		return nil, nil
	}
	repo := postgres.NewPositionRepo(db)
	for _, status := range []domain.PositionStatus{domain.StatusOpen, domain.StatusOpening} {
		positions, err := repo.FindByPoolAndStatus(ctx, poolID, status)
		if err != nil {
			return nil, err
		}
		if len(positions) > 0 {
			return positions[0], nil
		}
	}
	return nil, nil
}

func refreshExistingSolanaOpenPositionMetadata(ctx context.Context, cfg *config.Config, db *sql.DB, pos *domain.Position, poolMeta *ports.PoolDiscovery, maxPriorityLamports uint64) (*domain.Position, error) {
	if cfg == nil || db == nil || pos == nil || strings.TrimSpace(pos.PoolID) == "" {
		return pos, nil
	}
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	poolPubkey, err := solanago.PublicKeyFromBase58(strings.TrimSpace(pos.PoolID))
	if err != nil {
		return pos, err
	}
	state, err := fetchPancakeSolanaPoolState(ctx, client, poolPubkey)
	if err != nil {
		return pos, err
	}
	positionMint, mintErr := solanago.PublicKeyFromBase58(strings.TrimSpace(pos.TokenID))
	liquidityRaw := "0"
	tokenFeesOwed0Raw := uint64(0)
	tokenFeesOwed1Raw := uint64(0)
	rewardAmountsOwedRaw := make([]uint64, 0, 4)
	if mintErr == nil {
		if personal, personalErr := fetchPancakeSolanaPersonalPositionState(ctx, client, positionMint); personalErr == nil {
			liquidityRaw = personal.LiquidityRaw
			tokenFeesOwed0Raw = personal.TokenFeesOwed0
			tokenFeesOwed1Raw = personal.TokenFeesOwed1
			rewardAmountsOwedRaw = append(rewardAmountsOwedRaw, personal.RewardAmountsOwed...)
		}
	}
	rangeSummary, feeProjection, exitSignal := computeSolanaLPAnalytics(ctx, pos.PoolID, pos.Protocol, poolMeta, state, int32(pos.TickLower), int32(pos.TickUpper), pos.AmountUSD, maxPriorityLamports)
	var existing solanaLPPositionMetadata
	existingOK := false
	if strings.TrimSpace(pos.MetadataJSON) != "" {
		if json.Unmarshal([]byte(pos.MetadataJSON), &existing) == nil {
			existingOK = true
		}
	}
	if existingOK {
		if feeProjection.FeeBPS == 0 && existing.FeeBPS > 0 {
			feeProjection.FeeBPS = existing.FeeBPS
		}
		if feeProjection.PoolTVLUSD.IsZero() && strings.TrimSpace(existing.PoolTVLUSD) != "" {
			feeProjection.PoolTVLUSD = domain.MustDecimal(existing.PoolTVLUSD)
		}
		if feeProjection.PoolVol24hUSD.IsZero() && strings.TrimSpace(existing.PoolVol24hUSD) != "" {
			feeProjection.PoolVol24hUSD = domain.MustDecimal(existing.PoolVol24hUSD)
		}
		if feeProjection.EstimatedSharePct.IsZero() && strings.TrimSpace(existing.EstimatedSharePct) != "" {
			feeProjection.EstimatedSharePct = domain.MustDecimal(existing.EstimatedSharePct)
		}
		if rangeSummary.CurrentPrice.IsZero() && strings.TrimSpace(existing.CurrentPrice) != "" {
			rangeSummary.CurrentPrice = domain.MustDecimal(existing.CurrentPrice)
		}
		if rangeSummary.LowerPrice.IsZero() && strings.TrimSpace(existing.LowerPrice) != "" {
			rangeSummary.LowerPrice = domain.MustDecimal(existing.LowerPrice)
		}
		if rangeSummary.UpperPrice.IsZero() && strings.TrimSpace(existing.UpperPrice) != "" {
			rangeSummary.UpperPrice = domain.MustDecimal(existing.UpperPrice)
		}
	}
	meta := solanaLPPositionMetadata{
		Protocol:              pos.Protocol,
		PoolID:                pos.PoolID,
		PositionNFTMint:       pos.TokenID,
		OpenTxHash:            pos.OpenTxHash,
		PositionLiquidityRaw:  liquidityRaw,
		TokenFeesOwed0Raw:     tokenFeesOwed0Raw,
		TokenFeesOwed1Raw:     tokenFeesOwed1Raw,
		RewardAmountsOwedRaw:  rewardAmountsOwedRaw,
		TargetTotalUSD:        pos.AmountUSD.String(),
		CurrentTick:           rangeSummary.CurrentTick,
		TickLower:             rangeSummary.TickLower,
		TickUpper:             rangeSummary.TickUpper,
		CurrentPrice:          rangeSummary.CurrentPrice.String(),
		LowerPrice:            rangeSummary.LowerPrice.String(),
		UpperPrice:            rangeSummary.UpperPrice.String(),
		WidthBPS:              rangeSummary.WidthBPS.String(),
		DistanceLowerBPS:      rangeSummary.DistanceLowerBPS.String(),
		DistanceUpperBPS:      rangeSummary.DistanceUpperBPS.String(),
		BoundaryWarningBPS:    rangeSummary.BoundaryWarningBPS.String(),
		OccupancyFactor:       rangeSummary.OccupancyFactor.String(),
		InRange:               rangeSummary.InRange,
		FeeBPS:                feeProjection.FeeBPS,
		PoolTVLUSD:            feeProjection.PoolTVLUSD.String(),
		PoolVol24hUSD:         feeProjection.PoolVol24hUSD.String(),
		EstimatedSharePct:     feeProjection.EstimatedSharePct.String(),
		EstimatedFee24hUSD:    feeProjection.EstimatedFee24hUSD.String(),
		EstimatedAPR:          feeProjection.EstimatedAPR.String(),
		ExitAction:            exitSignal.Action,
		ExitReason:            exitSignal.Reason,
		ExpectedCloseCostUSD:  exitSignal.ExpectedCloseCostUSD.String(),
		ExpectedNetEdge24hUSD: exitSignal.ExpectedNetEdge24hUSD.String(),
	}
	if existingOK {
		meta.Token0Mint = existing.Token0Mint
		meta.Token1Mint = existing.Token1Mint
		meta.Token0MaxRaw = existing.Token0MaxRaw
		meta.Token1MaxRaw = existing.Token1MaxRaw
	}
	raw, err := json.Marshal(meta)
	if err != nil {
		return pos, err
	}
	updated := *pos
	updated.MetadataJSON = string(raw)
	if err := postgres.NewPositionRepo(db).Save(ctx, &updated); err != nil {
		return pos, err
	}
	return &updated, nil
}

func loadSolanaLPPositionMetadata(pos *domain.Position) (solanaLPPositionMetadata, bool) {
	if pos == nil || strings.TrimSpace(pos.MetadataJSON) == "" {
		return solanaLPPositionMetadata{}, false
	}
	var meta solanaLPPositionMetadata
	if err := json.Unmarshal([]byte(pos.MetadataJSON), &meta); err != nil {
		return solanaLPPositionMetadata{}, false
	}
	return meta, true
}

func applySolanaLPMetadataToPreflight(result *solanaLPPreflight, pos *domain.Position, meta solanaLPPositionMetadata) {
	if result == nil {
		return
	}
	positionValue := domain.ZeroDecimal()
	if pos != nil && pos.AmountUSD.GreaterThan(domain.ZeroDecimal()) {
		positionValue = pos.AmountUSD
	} else if strings.TrimSpace(meta.TargetTotalUSD) != "" {
		positionValue = domain.MustDecimal(meta.TargetTotalUSD)
	}
	currentPrice := solanaMetadataDecimalOr(meta.CurrentPrice, domain.ZeroDecimal())
	lowerPrice := solanaMetadataDecimalOr(meta.LowerPrice, domain.ZeroDecimal())
	upperPrice := solanaMetadataDecimalOr(meta.UpperPrice, domain.ZeroDecimal())
	widthBPS := solanaMetadataDecimalOr(meta.WidthBPS, domain.ZeroDecimal())
	distLower := solanaMetadataDecimalOr(meta.DistanceLowerBPS, domain.ZeroDecimal())
	distUpper := solanaMetadataDecimalOr(meta.DistanceUpperBPS, domain.ZeroDecimal())
	boundaryWarning := solanaMetadataDecimalOr(meta.BoundaryWarningBPS, domain.ZeroDecimal())
	occupancy := solanaMetadataDecimalOr(meta.OccupancyFactor, domain.ZeroDecimal())
	poolTVL := solanaMetadataDecimalOr(meta.PoolTVLUSD, domain.ZeroDecimal())
	poolVol := solanaMetadataDecimalOr(meta.PoolVol24hUSD, domain.ZeroDecimal())
	sharePct := solanaMetadataDecimalOr(meta.EstimatedSharePct, domain.ZeroDecimal())
	estimatedFee := solanaMetadataDecimalOr(meta.EstimatedFee24hUSD, domain.ZeroDecimal())
	estimatedAPR := solanaMetadataDecimalOr(meta.EstimatedAPR, domain.ZeroDecimal())
	expectedCloseCost := solanaMetadataDecimalOr(meta.ExpectedCloseCostUSD, domain.ZeroDecimal())
	expectedNetEdge := solanaMetadataDecimalOr(meta.ExpectedNetEdge24hUSD, domain.ZeroDecimal())
	inRange := meta.InRange
	nearBoundary := false
	if inRange && !boundaryWarning.IsZero() {
		nearBoundary = solanaMinDecimal(distLower, distUpper).LessThanOrEqual(boundaryWarning)
	}
	outOfRange := !inRange
	result.RangeSummary = solanaLPRangeSummary{
		CurrentTick:        meta.CurrentTick,
		TickLower:          meta.TickLower,
		TickUpper:          meta.TickUpper,
		CurrentPrice:       currentPrice,
		LowerPrice:         lowerPrice,
		UpperPrice:         upperPrice,
		WidthBPS:           widthBPS,
		DistanceLowerBPS:   distLower,
		DistanceUpperBPS:   distUpper,
		BoundaryWarningBPS: boundaryWarning,
		OccupancyFactor:    occupancy,
		InRange:            inRange,
	}
	result.FeeProjection = solanaLPFeeProjection{
		FeeBPS:             meta.FeeBPS,
		PoolTVLUSD:         poolTVL,
		PoolVol24hUSD:      poolVol,
		PositionValueUSD:   positionValue,
		EstimatedSharePct:  sharePct,
		EstimatedFee24hUSD: estimatedFee,
		EstimatedAPR:       estimatedAPR,
	}
	result.ExitSignal = solanaLPExitSignal{
		Action:                strings.TrimSpace(meta.ExitAction),
		Reason:                strings.TrimSpace(meta.ExitReason),
		NearBoundary:          nearBoundary,
		OutOfRange:            outOfRange,
		ExpectedCloseCostUSD:  expectedCloseCost,
		ExpectedNetEdge24hUSD: expectedNetEdge,
	}
	if strings.TrimSpace(result.ExitSignal.Action) == "" {
		result.ExitSignal = deriveSolanaLPExitSignal(result.RangeSummary, result.FeeProjection, expectedCloseCost)
	}
}

func solanaMetadataDecimalOr(raw string, fallback domain.Decimal) domain.Decimal {
	if strings.TrimSpace(raw) == "" {
		return fallback
	}
	return domain.MustDecimal(raw)
}

func runSolanaLPClosePreflight(ctx context.Context, cfg *config.Config, maxPriorityLamports uint64) error {
	report, err := inspectExistingSolanaLPCloseCandidate(ctx, cfg, maxPriorityLamports)
	if err != nil {
		return err
	}
	printSolanaLPClosePreflight(report)
	if recordErr := recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_preflight", "preflight", ""); recordErr != nil {
		fmt.Printf("solana_lp_close_preflight_record warning=%q\n", recordErr)
	}
	return nil
}

func inspectExistingSolanaLPCloseCandidate(ctx context.Context, cfg *config.Config, maxPriorityLamports uint64) (solanaLPClosePreflight, error) {
	if err := maybeBackfillLatestSolanaOpenCanaryPosition(ctx, cfg, maxPriorityLamports); err != nil {
		fmt.Printf("solana_lp_close_backfill warning=%q\n", err)
	}
	report := solanaLPClosePreflight{
		PoolID:   solanaKnownSOLUSDCPool,
		Protocol: "pancakeswap-v3-solana",
	}
	if pool, err := discoverPreferredSolanaLPPool(ctx); err == nil && pool != nil && strings.TrimSpace(pool.ID) != "" {
		report.PoolID = pool.ID
		report.Protocol = pool.Protocol
	}
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		report.Blocker = "postgres_dsn_missing"
		return report, nil
	}
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return report, err
	}
	defer store.Close()
	pos, err := findExistingOpenSolanaPositionForPool(ctx, store.DB(), report.PoolID)
	if err != nil {
		return report, err
	}
	if pos == nil {
		report.Blocker = "no_existing_open_position"
		return report, nil
	}
	if refreshed, refreshErr := refreshExistingSolanaOpenPositionMetadata(ctx, cfg, store.DB(), pos, lookupSolanaPoolDiscovery(ctx, report.PoolID, report.Protocol), maxPriorityLamports); refreshErr == nil && refreshed != nil {
		pos = refreshed
	}
	report.Position = pos
	if meta, ok := loadSolanaLPPositionMetadata(pos); ok {
		report.Metadata = meta
		report.CloseCandidate = strings.EqualFold(strings.TrimSpace(meta.ExitAction), "exit_now")
	}
	report.DecreaseBlocker = "solana_pancakeswap_v3_solana_decrease_liquidity_adapter_not_implemented"
	report.CollectBlocker = "solana_pancakeswap_v3_solana_collect_remaining_rewards_adapter_not_implemented"
	if report.CloseCandidate && strings.EqualFold(strings.TrimSpace(report.Protocol), "pancakeswap-v3-solana") {
		rewardsOwed := false
		for _, amount := range report.Metadata.RewardAmountsOwedRaw {
			if amount > 0 {
				rewardsOwed = true
				break
			}
		}
		if !rewardsOwed {
			report.CollectBuildReady = true
			report.CollectSignReady = true
			report.CollectSimReady = true
			report.CollectBlocker = ""
		}
		wallet := strings.TrimSpace(os.Getenv("SOLANA_FEE_PAYER_ADDRESS"))
		if wallet == "" {
			if key, _, ok, keyErr := loadSolanaPrivateKeyFromEnv(); keyErr == nil && ok {
				wallet = key.PublicKey().String()
			}
		}
		if wallet != "" {
			walletPubkey, parseErr := solanago.PublicKeyFromBase58(wallet)
			if parseErr == nil {
				if build, buildErr := buildPancakeSolanaDecreaseLiquidityTransaction(ctx, cfg, pos.TokenID, report.PoolID, walletPubkey); buildErr == nil {
					report.DecreaseBuildReady = true
					if key, _, ok, keyErr := loadSolanaPrivateKeyFromEnv(); keyErr == nil && ok {
						if signature, signErr := signPancakeSolanaDecreaseLiquidityTransaction(build.Tx, key); signErr == nil {
							_ = signature
							report.DecreaseSignReady = true
							client := solrpc.New(solanaReadinessEndpoint(cfg))
							simResp, simErr := client.SimulateTransactionWithOpts(ctx, build.Tx, &solrpc.SimulateTransactionOpts{
								SigVerify:              false,
								Commitment:             solrpc.CommitmentProcessed,
								ReplaceRecentBlockhash: true,
							})
							if simErr == nil && simResp != nil && simResp.Value != nil {
								if simResp.Value.Err == nil {
									report.DecreaseSimReady = true
									report.DecreaseBlocker = ""
								} else {
									report.DecreaseBlocker = fmt.Sprintf("%v", simResp.Value.Err)
								}
							} else if simErr != nil {
								report.DecreaseBlocker = simErr.Error()
							}
						} else {
							report.DecreaseBlocker = signErr.Error()
						}
					}
				} else {
					report.DecreaseBlocker = buildErr.Error()
				}
				if build, buildErr := buildPancakeSolanaClosePositionTransaction(ctx, cfg, pos.TokenID, report.PoolID, walletPubkey); buildErr == nil {
					report.CloseBuildReady = true
					report.CloseTxBase64Len = len(build.TxBase64)
					if key, _, ok, keyErr := loadSolanaPrivateKeyFromEnv(); keyErr == nil && ok {
						if signature, signErr := signPancakeSolanaClosePositionTransaction(build.Tx, key); signErr == nil {
							report.CloseSignReady = true
							report.CloseSignature = signature
							client := solrpc.New(solanaReadinessEndpoint(cfg))
							simResp, simErr := client.SimulateTransactionWithOpts(ctx, build.Tx, &solrpc.SimulateTransactionOpts{
								SigVerify:               false,
								Commitment:              solrpc.CommitmentProcessed,
								ReplaceRecentBlockhash:  true,
							})
							if simErr == nil && simResp != nil && simResp.Value != nil {
								if simResp.Value.Err == nil {
									report.CloseSimReady = true
									report.CloseSimUnits = derefUint64(simResp.Value.UnitsConsumed)
								} else {
									report.CloseSimErr = fmt.Sprintf("%v", simResp.Value.Err)
									report.CloseBlocker = report.CloseSimErr
								}
							} else if simErr != nil {
								report.CloseBlocker = simErr.Error()
							}
						}
					} else if keyErr != nil {
						report.CloseBlocker = keyErr.Error()
					}
				} else {
					report.CloseBlocker = buildErr.Error()
				}
			}
		}
	}
	report.FullExitPathReady = report.DecreaseSimReady && report.CollectSimReady && report.CloseSimReady
	return report, nil
}

func printSolanaLPClosePreflight(report solanaLPClosePreflight) {
	fmt.Printf("solana_lp_close_preflight close_candidate=%t pool_id=%s protocol=%s",
		report.CloseCandidate,
		report.PoolID,
		report.Protocol,
	)
	if report.Position != nil {
		fmt.Printf(" position_id=%s status=%s open_tx_hash=%s", shortAddress(report.Position.ID), report.Position.Status, shortAddress(report.Position.OpenTxHash))
	}
	if report.Blocker != "" {
		fmt.Printf(" blocker=%q", report.Blocker)
	}
	fmt.Println()
	if report.Position == nil {
		return
	}
	meta := report.Metadata
	if strings.TrimSpace(meta.ExitAction) != "" || strings.TrimSpace(meta.ExitReason) != "" {
		fmt.Printf("solana_lp_close_signal action=%s reason=%s in_range=%t liquidity_raw=%s fees_owed0_raw=%d fees_owed1_raw=%d rewards_owed_raw=%v current_price=%s lower_price=%s upper_price=%s expected_fee_24h_usd=%s expected_close_cost_usd=%s expected_net_edge_24h_usd=%s\n",
			meta.ExitAction,
			meta.ExitReason,
			meta.InRange,
			strings.TrimSpace(meta.PositionLiquidityRaw),
			meta.TokenFeesOwed0Raw,
			meta.TokenFeesOwed1Raw,
			meta.RewardAmountsOwedRaw,
			strings.TrimSpace(meta.CurrentPrice),
			strings.TrimSpace(meta.LowerPrice),
			strings.TrimSpace(meta.UpperPrice),
			strings.TrimSpace(meta.EstimatedFee24hUSD),
			strings.TrimSpace(meta.ExpectedCloseCostUSD),
			strings.TrimSpace(meta.ExpectedNetEdge24hUSD),
		)
	}
	fmt.Printf("solana_lp_close_readiness build_ready=%t sign_ready=%t sim_ready=%t", report.CloseBuildReady, report.CloseSignReady, report.CloseSimReady)
	if report.CloseTxBase64Len > 0 {
		fmt.Printf(" tx_base64_len=%d", report.CloseTxBase64Len)
	}
	if strings.TrimSpace(report.CloseSignature) != "" {
		fmt.Printf(" signature=%s", shortAddress(report.CloseSignature))
	}
	if report.CloseSimUnits > 0 {
		fmt.Printf(" sim_units=%d", report.CloseSimUnits)
	}
	if strings.TrimSpace(report.CloseSimErr) != "" {
		fmt.Printf(" sim_err=%q", report.CloseSimErr)
	}
	fmt.Println()
	fmt.Printf("solana_lp_exit_path decrease_build_ready=%t decrease_sign_ready=%t decrease_sim_ready=%t decrease_blocker=%q collect_build_ready=%t collect_sign_ready=%t collect_sim_ready=%t collect_blocker=%q close_build_ready=%t close_sign_ready=%t close_sim_ready=%t close_blocker=%q full_exit_path_ready=%t\n",
		report.DecreaseBuildReady,
		report.DecreaseSignReady,
		report.DecreaseSimReady,
		report.DecreaseBlocker,
		report.CollectBuildReady,
		report.CollectSignReady,
		report.CollectSimReady,
		report.CollectBlocker,
		report.CloseBuildReady,
		report.CloseSignReady,
		report.CloseSimReady,
		report.CloseBlocker,
		report.FullExitPathReady,
	)
}

func recordSolanaLPCloseInspection(ctx context.Context, cfg *config.Config, report solanaLPClosePreflight, command string, stage string, errorMsg string) error {
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		return nil
	}
	writer, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer writer.Close()
	event := canaryEvent{
		Chain:     domain.ChainSolana.String(),
		Command:   command,
		Stage:     stage,
		Status:    "ok",
		PoolID:    report.PoolID,
		Message:   fmt.Sprintf("close_candidate=%t action=%s reason=%s decrease_sim_ready=%t collect_sim_ready=%t close_sim_ready=%t full_exit_path_ready=%t", report.CloseCandidate, report.Metadata.ExitAction, report.Metadata.ExitReason, report.DecreaseSimReady, report.CollectSimReady, report.CloseSimReady, report.FullExitPathReady),
		ErrorMsg:  errorMsg,
		CreatedAt: time.Now().Unix(),
	}
	if strings.TrimSpace(errorMsg) != "" || strings.TrimSpace(report.Blocker) != "" {
		event.Status = "blocked"
		if strings.TrimSpace(errorMsg) == "" {
			event.ErrorMsg = report.Blocker
		}
	}
	if report.Position != nil {
		event.PositionID = report.Position.ID
		event.TokenID = report.Position.TokenID
		event.TxHash = report.Position.OpenTxHash
		event.AmountUSD = report.Position.AmountUSD.String()
	}
	return writer.Record(ctx, event)
}

func decodeSolanaOpenPositionFromStoredTx(ctx context.Context, db *sql.DB, txHash string) (reconciledSolanaOpenPosition, error) {
	repo := postgres.NewTxRepo(db)
	tx, err := repo.GetTxByHash(ctx, domain.ChainSolana, txHash)
	if err != nil {
		return reconciledSolanaOpenPosition{}, err
	}
	decoded, err := solanago.TransactionFromBytes(tx.Signature)
	if err != nil {
		return reconciledSolanaOpenPosition{}, fmt.Errorf("decode stored solana tx bytes: %w", err)
	}
	programID := solanago.MustPublicKeyFromBase58(pancakeswapSolanaCLMMProgramID)
	for _, inst := range decoded.Message.Instructions {
		pid, err := decoded.ResolveProgramIDIndex(inst.ProgramIDIndex)
		if err != nil || !pid.Equals(programID) {
			continue
		}
		data := inst.Data
		if len(data) < 59 || len(inst.Accounts) < 5 {
			continue
		}
		raw := []byte(data)
		if !bytesEqualPrefix(raw, pancakeOpenPositionWithToken22NftDiscriminator) {
			continue
		}
		nftMint := decoded.Message.AccountKeys[inst.Accounts[2]].String()
		poolID := decoded.Message.AccountKeys[inst.Accounts[4]].String()
		return reconciledSolanaOpenPosition{
			PositionID: nftMint,
			PoolID:     poolID,
			Protocol:   "pancakeswap-v3-solana",
			TickLower:  int32(binary.LittleEndian.Uint32(raw[8:12])),
			TickUpper:  int32(binary.LittleEndian.Uint32(raw[12:16])),
			Amount0Max: binary.LittleEndian.Uint64(raw[40:48]),
			Amount1Max: binary.LittleEndian.Uint64(raw[48:56]),
			BaseFlag:   raw[58] == 1,
			TxHash:     txHash,
		}, nil
	}
	return reconciledSolanaOpenPosition{}, fmt.Errorf("pancake solana open position instruction not found in tx %s", txHash)
}

func bytesEqualPrefix(data []byte, prefix []byte) bool {
	if len(data) < len(prefix) {
		return false
	}
	for i := range prefix {
		if data[i] != prefix[i] {
			return false
		}
	}
	return true
}

func lookupSolanaPoolDiscovery(ctx context.Context, poolID string, protocol string) *ports.PoolDiscovery {
	poolID = strings.TrimSpace(poolID)
	if poolID == "" {
		return &ports.PoolDiscovery{ID: poolID, Chain: domain.ChainSolana, Protocol: protocol}
	}
	gecko := geckoterminal.NewAdapter()
	if pool, err := gecko.GetPoolMetadata(ctx, domain.ChainSolana, poolID); err == nil && pool != nil {
		return pool
	}
	fallback := dexscreener.NewAdapter()
	if pool, err := fallback.GetPoolMetadata(ctx, domain.ChainSolana, poolID); err == nil && pool != nil {
		return pool
	}
	return &ports.PoolDiscovery{ID: poolID, Chain: domain.ChainSolana, Protocol: protocol}
}

func estimateSolanaLPCloseCostUSD(solPriceUSD domain.Decimal, maxPriorityLamports uint64) domain.Decimal {
	lamports := domain.NewDecimalFromInt(int64((solanaBaseNetworkFeeLamports + maxPriorityLamports) * 2))
	return lamports.Div(domain.MustDecimal("1000000000")).Mul(solPriceUSD)
}

func solanaMinDecimal(a, b domain.Decimal) domain.Decimal {
	if a.LessThan(b) {
		return a
	}
	return b
}

func solanaMaxDecimal(a, b domain.Decimal) domain.Decimal {
	if a.GreaterThan(b) {
		return a
	}
	return b
}

func decimalFromFloat(value float64) domain.Decimal {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return domain.ZeroDecimal()
	}
	return domain.NewDecimalFromFloat(value)
}
