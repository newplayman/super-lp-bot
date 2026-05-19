package log

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// NewLogger creates a zap logger with JSON output, fixed fields, and level filtering.
//
// Parameters:
//   - level: log level (debug, info, warn, error). Invalid levels fall back to info.
//   - env: environment identifier (dryrun, shadow, live).
//
// The returned logger includes fixed fields:
//   - env: the provided environment string
//   - schema_version: always set to 1
//
// Uses zap.NewProduction() as the base configuration.
func NewLogger(level string, env string) *zap.Logger {
	// Parse the log level
	var logLevel zapcore.Level
	switch level {
	case "debug":
		logLevel = zapcore.DebugLevel
	case "info":
		logLevel = zapcore.InfoLevel
	case "warn", "warning":
		logLevel = zapcore.WarnLevel
	case "error":
		logLevel = zapcore.ErrorLevel
	case "fatal":
		logLevel = zapcore.FatalLevel
	default:
		// Invalid level, fall back to info
		logLevel = zapcore.InfoLevel
	}

	// Create base config from NewProduction
	config := zap.NewProductionConfig()

	// Force JSON encoder (NewProduction already uses JSON, but being explicit)
	config.EncoderConfig = zap.NewProductionEncoderConfig()

	// Set the log level
	config.Level = zap.NewAtomicLevelAt(logLevel)

	// Build the base logger
	logger, err := config.Build()
	if err != nil {
		// Fall back to a no-op logger if build fails
		return zap.NewNop()
	}

	// Add fixed fields: env and schema_version
	logger = logger.With(
		zap.String("env", env),
		zap.Int("schema_version", 1),
	)

	return logger
}