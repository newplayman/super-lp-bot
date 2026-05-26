package main

import (
	"encoding/hex"
	"strings"
	"testing"
)

func TestDecodeERC20StringResult(t *testing.T) {
	for _, tc := range []struct {
		name    string
		hexData string
		want    string
		wantErr string
	}{
		{
			name: "dynamic string result",
			hexData: "" +
				"0000000000000000000000000000000000000000000000000000000000000020" +
				"0000000000000000000000000000000000000000000000000000000000000004" +
				"504c415900000000000000000000000000000000000000000000000000000000",
			want: "PLAY",
		},
		{
			name:    "fixed bytes32 result",
			hexData: "5553414400000000000000000000000000000000000000000000000000000000",
			want:    "USAD",
		},
		{
			name:    "invalid short result",
			hexData: "01",
			wantErr: "unrecognized",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			data := mustDecodeHexString(t, tc.hexData)
			got, err := decodeERC20StringResult(data)
			if tc.wantErr != "" {
				if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
					t.Fatalf("expected error containing %q, got %v", tc.wantErr, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.want {
				t.Fatalf("expected %q, got %q", tc.want, got)
			}
		})
	}
}

func mustDecodeHexString(t *testing.T, value string) []byte {
	t.Helper()
	data, err := hex.DecodeString(value)
	if err != nil {
		t.Fatalf("decode hex: %v", err)
	}
	return data
}
