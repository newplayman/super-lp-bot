// Package telegram provides a Telegram-based alerter implementation.
//
// This is a Phase 1 stub that logs alerts rather than sending them via Telegram.
// Full Telegram integration will be added in a future phase.
package telegram

import (
	"log/slog"

	"github.com/lpbot/lpbot/internal/ports"
)

// alerter is a Telegram alerter implementation (Phase 1 stub).
// Currently logs alerts instead of sending them via Telegram API.
type alerter struct {
	chatID  int64
	token   string
	logger  *slog.Logger
}

// New creates a new Telegram alerter stub.
// The returned alerter logs alerts rather than sending via Telegram.
func New(token string, chatID int64, logger *slog.Logger) *alerter {
	return &alerter{
		token:  token,
		chatID: chatID,
		logger: logger,
	}
}

// SendAlert implements ports.Alerter.
// Phase 1: Logs the alert message instead of sending via Telegram API.
// TODO(bendu): Implement actual Telegram API integration.
func (a *alerter) SendAlert(level ports.AlertLevel, src, msg string) error {
	a.logger.Info("telegram-alert-stub",
		"level", level,
		"src", src,
		"msg", msg,
		"chat_id", a.chatID,
	)
	return nil
}

// Compile-time interface assertion
var _ ports.Alerter = (*alerter)(nil)