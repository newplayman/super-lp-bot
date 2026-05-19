package decimal_test

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/lpbot/lpbot/pkg/decimal"
)

func TestDecimal_Scan(t *testing.T) {
	var d decimal.Decimal
	err := d.Scan([]byte("123.456"))
	require.NoError(t, err)
	require.Equal(t, "123.456", d.String())

	err = d.Scan("789.012")
	require.NoError(t, err)
	require.Equal(t, "789.012", d.String())
}

func TestDecimal_ScanError(t *testing.T) {
	var d decimal.Decimal
	err := d.Scan([]byte("not-number"))
	require.Error(t, err)
}

func TestDecimal_Value(t *testing.T) {
	d, _ := decimal.FromString("99.99")
	v, err := d.Value()
	require.NoError(t, err)
	require.Equal(t, "99.99", v)
}