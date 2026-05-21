package redis

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/platform/metrics"
	goredis "github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

const (
	defaultHeartbeatInterval = 15 * time.Second
	defaultHeartbeatTTL      = 60 * time.Second
	defaultOpTimeout         = 5 * time.Second
	defaultPrefix            = "lpbot"
)

var (
	redisUp                 = metrics.Gauge("lpbot_redis_up", "Redis connectivity state (1=up, 0=down)")
	redisPingLatencySeconds = metrics.Gauge("lpbot_redis_ping_latency_seconds", "Latest Redis ping latency in seconds")
	redisHeartbeatUnix      = metrics.Gauge("lpbot_redis_heartbeat_unix", "Latest successful Redis heartbeat timestamp in Unix seconds")
	redisErrorsTotal        = metrics.CounterVec("lpbot_redis_errors_total", "Total Redis runtime errors", []string{"reason"})
)

// Config defines runtime Redis settings.
type Config struct {
	URL               string
	Prefix            string
	Mode              string
	HeartbeatInterval time.Duration
	HeartbeatTTL      time.Duration
}

// Runtime maintains a live Redis connection and periodic heartbeat.
type Runtime struct {
	client            *goredis.Client
	logger            *zap.Logger
	heartbeatKey      string
	heartbeatValue    string
	heartbeatInterval time.Duration
	heartbeatTTL      time.Duration
}

// New validates the Redis URL, connects, and performs an initial ping.
func New(ctx context.Context, logger *zap.Logger, cfg Config) (*Runtime, error) {
	if strings.TrimSpace(cfg.URL) == "" {
		return nil, fmt.Errorf("redis url is empty")
	}

	opt, err := goredis.ParseURL(cfg.URL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}

	client := goredis.NewClient(opt)
	runtime := &Runtime{
		client:            client,
		logger:            logger,
		heartbeatKey:      buildHeartbeatKey(cfg.Prefix, cfg.Mode),
		heartbeatValue:    buildHeartbeatValue(cfg.Mode),
		heartbeatInterval: withDefault(cfg.HeartbeatInterval, defaultHeartbeatInterval),
		heartbeatTTL:      withDefault(cfg.HeartbeatTTL, defaultHeartbeatTTL),
	}

	if err := runtime.check(ctx); err != nil {
		_ = client.Close()
		return nil, err
	}

	if logger != nil {
		logger.Info("Redis runtime initialized",
			zap.String("addr", opt.Addr),
			zap.String("heartbeat_key", runtime.heartbeatKey),
			zap.Duration("heartbeat_interval", runtime.heartbeatInterval),
			zap.Duration("heartbeat_ttl", runtime.heartbeatTTL))
	}

	return runtime, nil
}

// Run keeps the heartbeat key fresh until the context is canceled.
func (r *Runtime) Run(ctx context.Context) {
	if r == nil {
		return
	}

	r.update(ctx)

	ticker := time.NewTicker(r.heartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.update(ctx)
		}
	}
}

// Close releases the Redis client.
func (r *Runtime) Close() error {
	if r == nil || r.client == nil {
		return nil
	}
	return r.client.Close()
}

func (r *Runtime) update(ctx context.Context) {
	if err := r.check(ctx); err != nil {
		if r.logger != nil {
			r.logger.Warn("Redis health check failed", zap.Error(err))
		}
		return
	}

	opCtx, cancel := context.WithTimeout(ctx, defaultOpTimeout)
	defer cancel()

	if err := r.client.Set(opCtx, r.heartbeatKey, r.heartbeatValue, r.heartbeatTTL).Err(); err != nil {
		redisErrorsTotal.WithLabelValues("heartbeat_set").Inc()
		if r.logger != nil {
			r.logger.Warn("Redis heartbeat write failed", zap.Error(err), zap.String("heartbeat_key", r.heartbeatKey))
		}
		return
	}

	redisHeartbeatUnix.Set(float64(time.Now().Unix()))
}

func (r *Runtime) check(ctx context.Context) error {
	opCtx, cancel := context.WithTimeout(ctx, defaultOpTimeout)
	defer cancel()

	start := time.Now()
	if err := r.client.Ping(opCtx).Err(); err != nil {
		redisUp.Set(0)
		redisErrorsTotal.WithLabelValues("ping").Inc()
		return fmt.Errorf("ping redis: %w", err)
	}

	redisUp.Set(1)
	redisPingLatencySeconds.Set(time.Since(start).Seconds())
	return nil
}

func buildHeartbeatKey(prefix string, mode string) string {
	if strings.TrimSpace(prefix) == "" {
		prefix = defaultPrefix
	}
	if strings.TrimSpace(mode) == "" {
		mode = "unknown"
	}
	host, err := os.Hostname()
	if err != nil || strings.TrimSpace(host) == "" {
		host = "unknown-host"
	}
	return fmt.Sprintf("%s:%s:heartbeat:%s", prefix, mode, host)
}

func buildHeartbeatValue(mode string) string {
	host, err := os.Hostname()
	if err != nil || strings.TrimSpace(host) == "" {
		host = "unknown-host"
	}
	if strings.TrimSpace(mode) == "" {
		mode = "unknown"
	}
	return fmt.Sprintf("mode=%s host=%s", mode, host)
}

func withDefault(value time.Duration, fallback time.Duration) time.Duration {
	if value <= 0 {
		return fallback
	}
	return value
}
