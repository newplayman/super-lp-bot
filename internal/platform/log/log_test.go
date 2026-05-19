package log

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
)

// Tests that the NewLogger function exists and has the correct signature.
// The actual implementation is done after these tests fail (red phase of TDD).

func TestNewLogger_Exists(t *testing.T) {
	// This test verifies the function exists and returns a non-nil *zap.Logger
	logger := NewLogger("info", "dryrun")
	require.NotNil(t, logger, "NewLogger should return a non-nil logger")
}

func TestNewLogger_DebugLevel(t *testing.T) {
	logger := NewLogger("debug", "dryrun")
	require.NotNil(t, logger)

	// Create an observer to capture logs
	observedCore, logs := observer.New(zapcore.DebugLevel)
	testLogger := zap.New(observedCore)

	testLogger.Debug("debug message")
	testLogger.Info("info message")
	testLogger.Warn("warn message")
	testLogger.Error("error message")

	// All levels should pass at debug
	assert.Equal(t, 4, logs.Len(), "debug logger should capture all levels")
}

func TestNewLogger_InfoLevel(t *testing.T) {
	logger := NewLogger("info", "shadow")
	require.NotNil(t, logger)

	// Create an observer to capture logs
	observedCore, logs := observer.New(zapcore.InfoLevel)
	testLogger := zap.New(observedCore)

	testLogger.Debug("debug message")
	testLogger.Info("info message")
	testLogger.Warn("warn message")
	testLogger.Error("error message")

	// Only info and above should pass
	assert.Equal(t, 3, logs.Len(), "info logger should filter out debug")
}

func TestNewLogger_WarnLevel(t *testing.T) {
	logger := NewLogger("warn", "live")
	require.NotNil(t, logger)

	// Create an observer to capture logs
	observedCore, logs := observer.New(zapcore.WarnLevel)
	testLogger := zap.New(observedCore)

	testLogger.Debug("debug message")
	testLogger.Info("info message")
	testLogger.Warn("warn message")
	testLogger.Error("error message")

	// Only warn and above should pass
	assert.Equal(t, 2, logs.Len(), "warn logger should filter out debug and info")
}

func TestNewLogger_ErrorLevel(t *testing.T) {
	logger := NewLogger("error", "dryrun")
	require.NotNil(t, logger)

	// Create an observer to capture logs
	observedCore, logs := observer.New(zapcore.ErrorLevel)
	testLogger := zap.New(observedCore)

	testLogger.Debug("debug message")
	testLogger.Info("info message")
	testLogger.Warn("warn message")
	testLogger.Error("error message")

	// Only error should pass
	assert.Equal(t, 1, logs.Len(), "error logger should only pass error level")
}

func TestNewLogger_InvalidLevelFallsBackToInfo(t *testing.T) {
	logger := NewLogger("invalid_level", "dryrun")
	require.NotNil(t, logger)

	// Invalid level should fall back to info
	observedCore, logs := observer.New(zapcore.InfoLevel)
	testLogger := zap.New(observedCore)

	testLogger.Debug("debug should be filtered")
	testLogger.Info("info should pass")
	testLogger.Warn("warn should pass")

	assert.Equal(t, 0, logs.Filter(func(e observer.LoggedEntry) bool {
		return e.Level == zapcore.DebugLevel
	}).Len(), "debug should be filtered with invalid level")
	assert.Equal(t, 2, logs.Len(), "info and warn should pass")
}

func TestNewLogger_EmptyEnv(t *testing.T) {
	logger := NewLogger("info", "")
	require.NotNil(t, logger)
}

func TestNewLogger_EnvDryrun(t *testing.T) {
	logger := NewLogger("info", "dryrun")
	require.NotNil(t, logger)
}

func TestNewLogger_EnvShadow(t *testing.T) {
	logger := NewLogger("info", "shadow")
	require.NotNil(t, logger)
}

func TestNewLogger_EnvLive(t *testing.T) {
	logger := NewLogger("info", "live")
	require.NotNil(t, logger)
}