package main

import (
	"testing"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestComputeLivePositionMarkPnL(t *testing.T) {
	for _, tc := range []struct {
		name             string
		entryValueUSD    string
		positionValueUSD string
		feeCollectedUSD  string
		feeUncollectedUSD string
		gasUSD           string
		holdValueUSD     string
		wantILUSD        string
		wantNetPnLUSD    string
	}{
		{
			name:              "price up produces negative il and positive net after fees",
			entryValueUSD:     "10",
			positionValueUSD:  "11",
			feeCollectedUSD:   "0.5",
			feeUncollectedUSD: "0.5",
			gasUSD:            "0.25",
			holdValueUSD:      "12.5",
			wantILUSD:         "-0.5",
			wantNetPnLUSD:     "1.75",
		},
		{
			name:              "price down can keep il near flat and net negative after gas",
			entryValueUSD:     "10",
			positionValueUSD:  "8.5",
			feeCollectedUSD:   "0.25",
			feeUncollectedUSD: "0.25",
			gasUSD:            "0.5",
			holdValueUSD:      "9",
			wantILUSD:         "0",
			wantNetPnLUSD:     "-1.5",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ilUSD, netPnLUSD := computeLivePositionMarkPnL(
				domain.MustDecimal(tc.entryValueUSD),
				domain.MustDecimal(tc.positionValueUSD),
				domain.MustDecimal(tc.feeCollectedUSD),
				domain.MustDecimal(tc.feeUncollectedUSD),
				domain.MustDecimal(tc.gasUSD),
				domain.MustDecimal(tc.holdValueUSD),
			)
			require.Equal(t, tc.wantILUSD, ilUSD.String())
			require.Equal(t, tc.wantNetPnLUSD, netPnLUSD.String())
		})
	}
}
