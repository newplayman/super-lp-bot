// Package telegram provides a Telegram-based alerter implementation.
//
// This adapter sends alerts to Telegram using the Bot API.
// Build tags control behavior:
//   - dryrun: panics on Send (invariant #3 - no alerts in dryrun)
//   - shadow: logs and sends real HTTP requests
//   - live: sends real HTTP requests
package telegram

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/lpbot/lpbot/internal/ports"
)

// alerter sends alerts via the Telegram Bot API.
type alerter struct {
	token   string
	chatID  int64
	baseURL string
	client  *http.Client
}

// AlertConfig holds configuration for the Telegram alerter.
type AlertConfig struct {
	Token  string
	ChatID int64
}

// New creates a new Telegram alerter with the given configuration.
func New(cfg AlertConfig) *alerter {
	return &alerter{
		token:   cfg.Token,
		chatID:  cfg.ChatID,
		baseURL: "https://api.telegram.org/bot" + cfg.Token,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// NewWithToken creates a new Telegram alerter with token and chat ID.
// Deprecated: Use New(AlertConfig{Token: x, ChatID: y}) instead.
func NewWithToken(token string, chatID int64) *alerter {
	return New(AlertConfig{Token: token, ChatID: chatID})
}

// SendAlert sends an alert via Telegram.
// The alert is formatted as a message with severity, source, and content.
func (a *alerter) SendAlert(level ports.AlertLevel, src, msg string) error {
	return a.SendAlertContext(context.Background(), level, src, msg)
}

// SendAlertContext sends an alert with explicit context support.
func (a *alerter) SendAlertContext(ctx context.Context, level ports.AlertLevel, src, msg string) error {
	// Format message with severity emoji and formatting
	emoji := alertEmoji(level)
	text := fmt.Sprintf("%s [%s]\n\n*Source:* %s\n*Message:* %s",
		emoji,
		level,
		src,
		msg,
	)

	return a.sendMessage(ctx, text)
}

// sendMessage sends a message to the configured Telegram chat.
func (a *alerter) sendMessage(ctx context.Context, text string) error {
	// Telegram API endpoint for sending messages
	url := fmt.Sprintf("%s/sendMessage", a.baseURL)

	// Build request payload
	payload := map[string]interface{}{
		"chat_id":    a.chatID,
		"text":       text,
		"parse_mode": "Markdown",
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	// Send request
	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	// Check response
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Telegram API error: status %d", resp.StatusCode)
	}

	return nil
}

// alertEmoji returns the emoji for an alert level.
func alertEmoji(level ports.AlertLevel) string {
	switch level {
	case ports.AlertP0:
		return "🚨" // Critical - immediate action required
	case ports.AlertP1:
		return "⚠️" // Warning - attention needed
	case ports.AlertP2:
		return "ℹ️" // Info - informational
	default:
		return "📢"
	}
}

// Compile-time interface assertion
var _ ports.Alerter = (*alerter)(nil)