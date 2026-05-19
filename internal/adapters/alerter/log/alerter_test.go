package logalerter

import (
	"bytes"
	"testing"

	"github.com/lpbot/lpbot/internal/ports"
	"github.com/stretchr/testify/require"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// bufferSyncer implements zapcore.WriteSyncer for testing
type bufferSyncer struct {
	buf bytes.Buffer
}

func (s *bufferSyncer) Write(p []byte) (int, error) {
	return s.buf.Write(p)
}

func (s *bufferSyncer) Sync() error { return nil }

func (s *bufferSyncer) String() string { return s.buf.String() }

func makeTestLogger(buf *bufferSyncer) *zap.Logger {
	core := zapcore.NewCore(
		zapcore.NewJSONEncoder(zapcore.EncoderConfig{
			TimeKey:        "time",
			LevelKey:       "level",
			MessageKey:     "msg",
			EncodeLevel:    zapcore.LowercaseLevelEncoder,
		}),
		buf,
		zapcore.DebugLevel,
	)
	return zap.New(core)
}

func TestAlerterSendAlert_P0(t *testing.T) {
	buf := &bufferSyncer{}
	log := makeTestLogger(buf)

	a := New(log)
	err := a.SendAlert(ports.AlertP0, "risk", "KILL: portfolio loss > 10%")
	require.NoError(t, err)

	require.Contains(t, buf.String(), `"level":"error"`)
	require.Contains(t, buf.String(), `"msg":"KILL: portfolio loss > 10%"`)
	require.Contains(t, buf.String(), `"alert_level":"p0"`)
	require.Contains(t, buf.String(), `"alert_src":"risk"`)
}

func TestAlerterSendAlert_P1(t *testing.T) {
	buf := &bufferSyncer{}
	log := makeTestLogger(buf)

	a := New(log)
	err := a.SendAlert(ports.AlertP1, "pool", "Single pool stop loss triggered")
	require.NoError(t, err)

	require.Contains(t, buf.String(), `"level":"warn"`)
	require.Contains(t, buf.String(), `"msg":"Single pool stop loss triggered"`)
	require.Contains(t, buf.String(), `"alert_level":"p1"`)
}

func TestAlerterSendAlert_P2(t *testing.T) {
	buf := &bufferSyncer{}
	log := makeTestLogger(buf)

	a := New(log)
	err := a.SendAlert(ports.AlertP2, "execution", "Position opened")
	require.NoError(t, err)

	require.Contains(t, buf.String(), `"level":"info"`)
	require.Contains(t, buf.String(), `"msg":"Position opened"`)
	require.Contains(t, buf.String(), `"alert_level":"p2"`)
}