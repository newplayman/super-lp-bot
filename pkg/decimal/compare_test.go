package decimal_test

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestCmp(t *testing.T) {
	a, _ := decimal.FromString("3")
	b, _ := decimal.FromString("5")
	require.Equal(t, -1, a.Cmp(b))
	require.Equal(t, 1, b.Cmp(a))
	require.Equal(t, 0, a.Cmp(a))
}

func TestGreaterThan(t *testing.T) {
	a, _ := decimal.FromString("5")
	b, _ := decimal.FromString("3")
	require.True(t, a.GreaterThan(b))
	require.False(t, a.GreaterThan(a))
}

func TestLessThan(t *testing.T) {
	a, _ := decimal.FromString("3")
	b, _ := decimal.FromString("5")
	require.True(t, a.LessThan(b))
	require.False(t, a.LessThan(a))
}

func TestGreaterThanOrEqual(t *testing.T) {
	a, _ := decimal.FromString("5")
	b, _ := decimal.FromString("5")
	c, _ := decimal.FromString("3")
	require.True(t, a.GreaterThanOrEqual(b))
	require.True(t, a.GreaterThanOrEqual(c))
	require.False(t, c.GreaterThanOrEqual(a))
}

func TestLessThanOrEqual(t *testing.T) {
	a, _ := decimal.FromString("5")
	b, _ := decimal.FromString("5")
	c, _ := decimal.FromString("3")
	require.True(t, a.LessThanOrEqual(b))
	require.True(t, c.LessThanOrEqual(a))
	require.False(t, a.LessThanOrEqual(c))
}

func TestEqual(t *testing.T) {
	a, _ := decimal.FromString("5")
	b, _ := decimal.FromString("5")
	c, _ := decimal.FromString("3")
	require.True(t, a.Equal(b))
	require.False(t, a.Equal(c))
}

func TestMin(t *testing.T) {
	a, _ := decimal.FromString("2")
	b, _ := decimal.FromString("5")
	require.Equal(t, "2.000000000000000000000000000000000000", decimal.Min(a, b).String())
	require.Equal(t, "2.000000000000000000000000000000000000", decimal.Min(b, a).String())
}

func TestMax(t *testing.T) {
	a, _ := decimal.FromString("2")
	b, _ := decimal.FromString("5")
	require.Equal(t, "5.000000000000000000000000000000000000", decimal.Max(a, b).String())
}
