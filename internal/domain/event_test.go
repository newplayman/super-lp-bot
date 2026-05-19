package domain_test

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestEvent_NewEvent(t *testing.T) {
	e, err := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, map[string]string{"pool": "0x123"})
	require.NoError(t, err)
	require.NotEmpty(t, e.EventID)
	require.NotEmpty(t, e.TraceID)
	require.Equal(t, "dryrun.pool.scored", e.Topic)
	require.Equal(t, domain.EnvDryrun, e.Env)
	require.Equal(t, 1, e.SchemaVersion)
	require.Nil(t, e.BlockRef)
}

func TestEvent_PayloadAs(t *testing.T) {
	e, _ := domain.NewEvent("test", domain.EnvDryrun, map[string]int{"value": 42})
	var m map[string]int
	err := e.PayloadAs(&m)
	require.NoError(t, err)
	require.Equal(t, 42, m["value"])
}

func TestEvent_String(t *testing.T) {
	e, _ := domain.NewEvent("dryrun.pool.scored", domain.EnvDryrun, nil)
	s := e.String()
	require.Contains(t, s, "dryrun.pool.scored")
	require.Contains(t, s, e.EventID[:8])
}

func TestEnv(t *testing.T) {
	require.Equal(t, "dryrun", domain.EnvDryrun.String())
	require.Equal(t, "shadow", domain.EnvShadow.String())
	require.Equal(t, "live", domain.EnvLive.String())
}