// Package logalerter provides a logging-based alerter implementation.
package logalerter

import (
	"go.uber.org/zap"

	"github.com/lpbot/lpbot/internal/ports"
)

// alerter is a logging-based alerter that outputs alerts via zap.Logger.
type alerter struct {
	log *zap.Logger
}

// New creates a new log-based alerter with the provided zap logger.
func New(log *zap.Logger) *alerter {
	return &alerter{log: log}
}

// SendAlert implements ports.Alerter by logging the alert at the appropriate level.
func (a *alerter) SendAlert(level ports.AlertLevel, src, msg string) error {
	zfs := []zap.Field{zap.String("alert_level", string(level)), zap.String("alert_src", src)}
	switch level {
	case ports.AlertP0:
		a.log.Error(msg, zfs...)
	case ports.AlertP1:
		a.log.Warn(msg, zfs...)
	case ports.AlertP2:
		a.log.Info(msg, zfs...)
	default:
		a.log.Info(msg, zfs...)
	}
	return nil
}

// Compile-time interface assertion
var _ ports.Alerter = (*alerter)(nil)