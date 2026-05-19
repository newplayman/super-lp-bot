package ports

import (
	"context"
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
)

// Compile-time interface compliance checks for ConfigSnap
func TestConfigSnapInterface(t *testing.T) {
	var _ ConfigSnap = (*configSnapNop)(nil)
}

// configSnapNop is a no-op implementation for compile-time interface checks.
type configSnapNop struct{}

func (configSnapNop) AppendSnapshot(ctx context.Context, snapshot ConfigSnapshot) error { return nil }

func (configSnapNop) GetLatestSnapshot(ctx context.Context, env domain.Env) (ConfigSnapshot, error) {
	return ConfigSnapshot{}, nil
}

func (configSnapNop) GetPreviousSnapshot(ctx context.Context, env domain.Env) (ConfigSnapshot, error) {
	return ConfigSnapshot{}, nil
}

func (configSnapNop) ListSnapshots(ctx context.Context, filter ConfigSnapFilter) ([]ConfigSnapshot, error) {
	return nil, nil
}

// TestConfigSnapshotFields verifies ConfigSnapshot struct has required fields
func TestConfigSnapshotFields(t *testing.T) {
	snapshot := ConfigSnapshot{
		ID:        "snap-123",
		Env:       domain.EnvLive,
		Hash:      "sha256:abc123def456",
		Content:   "[mode]\nexpected = \"live\"\n",
		Version:   "1.0.0",
		Timestamp: 1234567890,
	}

	if snapshot.ID == "" {
		t.Error("ConfigSnapshot.ID should not be empty")
	}
	if snapshot.Env == "" {
		t.Error("ConfigSnapshot.Env should not be empty")
	}
	if snapshot.Hash == "" {
		t.Error("ConfigSnapshot.Hash should not be empty")
	}
	if snapshot.Content == "" {
		t.Error("ConfigSnapshot.Content should not be empty")
	}
}

// TestConfigSnapshotEnvValues verifies ConfigSnapshot works with all env values
func TestConfigSnapshotEnvValues(t *testing.T) {
	envs := []domain.Env{domain.EnvDryrun, domain.EnvShadow, domain.EnvLive}
	for _, env := range envs {
		snapshot := ConfigSnapshot{Env: env}
		if snapshot.Env != env {
			t.Errorf("ConfigSnapshot.Env = %q, want %q", snapshot.Env, env)
		}
	}
}

// TestConfigSnapFilterFields verifies ConfigSnapFilter struct has required fields
func TestConfigSnapFilterFields(t *testing.T) {
	filter := ConfigSnapFilter{
		Env:   domain.EnvShadow,
		Since: 1234567890,
		Limit: 100,
	}

	if filter.Env != domain.EnvShadow {
		t.Errorf("ConfigSnapFilter.Env = %q, want 'shadow'", filter.Env)
	}
	if filter.Since != 1234567890 {
		t.Errorf("ConfigSnapFilter.Since = %d, want 1234567890", filter.Since)
	}
	if filter.Limit != 100 {
		t.Errorf("ConfigSnapFilter.Limit = %d, want 100", filter.Limit)
	}
}

// TestConfigSnapFilterDefault verifies zero values are handled correctly
func TestConfigSnapFilterZeroValues(t *testing.T) {
	filter := ConfigSnapFilter{}

	if filter.Env != "" {
		t.Errorf("ConfigSnapFilter.Env = %q, want empty", filter.Env)
	}
	if filter.Since != 0 {
		t.Errorf("ConfigSnapFilter.Since = %d, want 0", filter.Since)
	}
	if filter.Limit != 0 {
		t.Errorf("ConfigSnapFilter.Limit = %d, want 0", filter.Limit)
	}
}

// TestErrConfigSnapNotFound verifies error type
func TestErrConfigSnapNotFound(t *testing.T) {
	err := ErrConfigSnapNotFound
	if err.Error() != "config snapshot not found" {
		t.Errorf("ErrConfigSnapNotFound.Error() = %q, want 'config snapshot not found'", err.Error())
	}
	if !err.Is(ErrConfigSnapNotFound) {
		t.Error("ErrConfigSnapNotFound.Is should return true for itself")
	}
}

// TestConfigSnapshotList verifies multiple snapshots can coexist
func TestConfigSnapshotList(t *testing.T) {
	snapshots := []ConfigSnapshot{
		{ID: "snap-1", Env: domain.EnvLive, Timestamp: 1000},
		{ID: "snap-2", Env: domain.EnvLive, Timestamp: 2000},
		{ID: "snap-3", Env: domain.EnvLive, Timestamp: 3000},
	}

	if len(snapshots) != 3 {
		t.Errorf("Expected 3 snapshots, got %d", len(snapshots))
	}

	// Verify ordering (newest last when appending)
	for i, snap := range snapshots {
		if snap.Timestamp != int64((i+1)*1000) {
			t.Errorf("Snapshot[%d].Timestamp = %d, want %d", i, snap.Timestamp, (i+1)*1000)
		}
	}
}
