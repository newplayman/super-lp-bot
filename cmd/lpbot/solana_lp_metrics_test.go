package main

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

func TestBuildSolanaLPRangeSummary(t *testing.T) {
	state := pancakeswapSolanaPoolState{
		MintDecimals0: 9,
		MintDecimals1: 6,
		SqrtPriceX64:  ^uint64(0),
		CurrentTick:   0,
	}

	summary := buildSolanaLPRangeSummary(state, -100, 100)

	if !summary.InRange {
		t.Fatal("expected current price to be in range")
	}
	if summary.WidthBPS.LessThanOrEqual(domain.ZeroDecimal()) {
		t.Fatalf("expected positive width bps, got %s", summary.WidthBPS)
	}
	if !summary.LowerPrice.LessThan(summary.CurrentPrice) {
		t.Fatalf("expected lower price < current price, got %s >= %s", summary.LowerPrice, summary.CurrentPrice)
	}
	if !summary.UpperPrice.GreaterThan(summary.CurrentPrice) {
		t.Fatalf("expected upper price > current price, got %s <= %s", summary.UpperPrice, summary.CurrentPrice)
	}
}

func TestEstimateSolanaLPFeeProjection(t *testing.T) {
	rangeSummary := solanaLPRangeSummary{
		InRange:              true,
		OccupancyFactor:      domain.MustDecimal("1"),
		DistanceLowerBPS:     domain.MustDecimal("50"),
		DistanceUpperBPS:     domain.MustDecimal("50"),
		BoundaryWarningBPS:   domain.MustDecimal("10"),
	}

	projection := estimateSolanaLPFeeProjection(
		domain.MustDecimal("10"),
		30,
		domain.MustDecimal("100000"),
		domain.MustDecimal("1000000"),
		rangeSummary,
	)

	if !projection.EstimatedFee24hUSD.Equal(domain.MustDecimal("0.3")) {
		t.Fatalf("expected estimated fee 24h = 0.3, got %s", projection.EstimatedFee24hUSD)
	}
	if !projection.EstimatedSharePct.Equal(domain.MustDecimal("0.01")) {
		t.Fatalf("expected estimated share pct = 0.01, got %s", projection.EstimatedSharePct)
	}
	if !projection.EstimatedAPR.Equal(domain.MustDecimal("1095")) {
		t.Fatalf("expected estimated apr = 1095, got %s", projection.EstimatedAPR)
	}
}

func TestDeriveSolanaLPExitSignal(t *testing.T) {
	rangeSummary := solanaLPRangeSummary{
		InRange:            true,
		CurrentTick:        0,
		TickLower:          -100,
		TickUpper:          100,
		DistanceLowerBPS:   domain.MustDecimal("40"),
		DistanceUpperBPS:   domain.MustDecimal("40"),
		BoundaryWarningBPS: domain.MustDecimal("50"),
		OccupancyFactor:    domain.MustDecimal("0.1"),
	}
	projection := solanaLPFeeProjection{
		EstimatedFee24hUSD: domain.MustDecimal("0.01"),
	}

	signal := deriveSolanaLPExitSignal(rangeSummary, projection, domain.MustDecimal("0.05"))

	if signal.Action != "exit_now" {
		t.Fatalf("expected exit_now, got %q", signal.Action)
	}
	if signal.Reason != "near_boundary_negative_edge" {
		t.Fatalf("expected near_boundary_negative_edge, got %q", signal.Reason)
	}
}

func TestPancakeTradeFeeRateToBPS(t *testing.T) {
	if got := pancakeTradeFeeRateToBPS(2500); got != 25 {
		t.Fatalf("expected 25 bps, got %d", got)
	}
}
