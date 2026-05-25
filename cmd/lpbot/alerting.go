package main

import (
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"

	logalerter "github.com/lpbot/lpbot/internal/adapters/alerter/log"
	"github.com/lpbot/lpbot/internal/adapters/alerter/telegram"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

const defaultAlertMinInterval = 60 * time.Second

type alertThrottle struct {
	mu       sync.Mutex
	interval time.Duration
	lastSent map[string]time.Time
}

func newAlertThrottle(interval time.Duration) *alertThrottle {
	if interval <= 0 {
		interval = defaultAlertMinInterval
	}
	return &alertThrottle{
		interval: interval,
		lastSent: make(map[string]time.Time),
	}
}

func (t *alertThrottle) shouldSend(key string) bool {
	now := time.Now()
	t.mu.Lock()
	defer t.mu.Unlock()

	last := t.lastSent[key]
	if now.Sub(last) < t.interval {
		return false
	}
	t.lastSent[key] = now
	return true
}

type alertRouter struct {
	logger   *zap.Logger
	primary  ports.Alerter
	fallback ports.Alerter
	throttle *alertThrottle
}

func initAlerter(logger *zap.Logger, cfg *config.Config) ports.Alerter {
	logger = normalizeAlerterLogger(logger)
	interval := defaultAlertMinInterval
	if cfg != nil && cfg.Alerting.MinIntervalSeconds > 0 {
		interval = time.Duration(cfg.Alerting.MinIntervalSeconds) * time.Second
	}
	throttle := newAlertThrottle(interval)

	logAlerter := logalerter.New(logger)
	if cfg == nil {
		logger.Warn("alerting disabled: missing config, fallback to logs only")
		return &alertRouter{
			logger:   logger,
			primary:  logAlerter,
			fallback: logAlerter,
			throttle: throttle,
		}
	}

	token := strings.TrimSpace(cfg.Alerting.TelegramToken)
	chatID, err := parseTelegramChatID(cfg.Alerting.TelegramChatID)
	if err != nil {
		if token != "" {
			logger.Warn("alerting telegram chat id invalid, fallback to logs only", zap.String("err", err.Error()))
		}
	}

	if token == "" || err != nil || chatID == 0 {
		if token == "" {
			logger.Warn("telegram token missing, fallback to logs only")
		}
		return &alertRouter{
			logger:   logger,
			primary:  logAlerter,
			fallback: logAlerter,
			throttle: throttle,
		}
	}

	tgAlerter := telegram.New(telegram.AlertConfig{
		Token:  token,
		ChatID: chatID,
	})
	return &alertRouter{
		logger:   logger,
		primary:  tgAlerter,
		fallback: logAlerter,
		throttle: throttle,
	}
}

func parseTelegramChatID(raw string) (int64, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0, fmt.Errorf("telegram chat id empty")
	}
	chatID, err := strconv.ParseInt(value, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid telegram chat id: %w", err)
	}
	return chatID, nil
}

func (ar *alertRouter) SendAlert(level ports.AlertLevel, src, msg string) error {
	if ar == nil {
		return nil
	}
	key := strings.ToLower(strings.TrimSpace(string(level))) + "|" + strings.TrimSpace(src)
	if !ar.throttle.shouldSend(key) {
		return nil
	}

	if err := ar.primary.SendAlert(level, src, msg); err != nil {
		if ar.fallback != nil {
			_ = ar.fallback.SendAlert(level, src, msg)
		}
		if ar.logger != nil {
			ar.logger.Warn("alert primary delivery failed",
				zap.String("alert_level", string(level)),
				zap.String("src", src),
				zap.String("msg", msg),
				zap.Error(err))
		}
		return err
	}
	return nil
}

func normalizeAlerterLogger(logger *zap.Logger) *zap.Logger {
	if logger != nil {
		return logger
	}
	recovery, _ := zap.NewProduction()
	return recovery
}

func (app *App) sendAlert(level ports.AlertLevel, src, msg string) {
	if app == nil || app.alerter == nil {
		if app != nil && app.logger != nil {
			app.logger.Warn("alert dropped (alerter not initialized)",
				zap.String("alert_level", string(level)),
				zap.String("src", src),
				zap.String("msg", msg))
		}
		return
	}
	if err := app.alerter.SendAlert(level, src, msg); err != nil {
		if app.logger != nil {
			app.logger.Warn("failed to send alert",
				zap.String("alert_level", string(level)),
				zap.String("src", src),
				zap.String("msg", msg),
				zap.Error(err))
		}
	}
}
