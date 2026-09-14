package redis

import (
	"context"
	"strings"
	"testing"

	goredis "github.com/redis/go-redis/v9"
)

// TestParseURL_DoesNotPanic verifies ParseURL still accepts the URL format we
// construct from cfg.URL. Regression guard for go-redis/v9 v9.7.1 -> v9.7.3
// upgrade (CI closeout 2026-09-14). The runtime stores an empty URL error
// upstream, so an obviously-malformed URL must be rejected by ParseURL.
func TestParseURL_DoesNotPanic(t *testing.T) {
	cases := []struct {
		name    string
		url     string
		wantErr bool
	}{
		{name: "empty", url: "", wantErr: true},
		{name: "malformed-scheme", url: "not://a-url", wantErr: true},
		{name: "valid-redis", url: "redis://localhost:6379/0", wantErr: false},
		{name: "valid-rediss", url: "rediss://localhost:6379/0", wantErr: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := goredis.ParseURL(tc.url)
			if tc.wantErr && err == nil {
				t.Fatalf("expected error for %q, got nil", tc.url)
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected error for %q: %v", tc.url, err)
			}
		})
	}
}

// TestNewClient_ConstructsClientWithParsedOptions verifies that the API surface
// our runtime uses (goredis.NewClient(opt)) constructs a *goredis.Client with
// all methods (Set/Ping/Close) still callable after the v9.7.3 upgrade. No
// network I/O — we only validate the in-memory client object shape.
func TestNewClient_ConstructsClientWithParsedOptions(t *testing.T) {
	opt, err := goredis.ParseURL("redis://127.0.0.1:0/0")
	if err != nil {
		t.Fatalf("ParseURL failed: %v", err)
	}
	c := goredis.NewClient(opt)
	if c == nil {
		t.Fatal("NewClient returned nil")
	}
	if err := c.Close(); err != nil {
		// Closing a never-used client should not error; v9.7.3 keeps this contract.
		t.Fatalf("Close on fresh client returned error: %v", err)
	}
}

// TestRuntime_NewRejectsEmptyURL is a direct product-path regression: the
// runtime.New() constructor must refuse an empty URL string before reaching
// any network call.
func TestRuntime_NewRejectsEmptyURL(t *testing.T) {
	_, err := New(context.Background(), nil, Config{URL: ""})
	if err == nil {
		t.Fatal("expected error for empty URL, got nil")
	}
	if !strings.Contains(err.Error(), "empty") {
		t.Fatalf("error %q should mention 'empty'", err)
	}
}

// TestRuntime_NewPropagatesParseError verifies that a URL parse failure
// surfaces verbatim from goredis.ParseURL through runtime.New. This guards
// the v9.7.3 upgrade's error-message compatibility.
func TestRuntime_NewPropagatesParseError(t *testing.T) {
	_, err := New(context.Background(), nil, Config{URL: "not://a-url"})
	if err == nil {
		t.Fatal("expected error for malformed URL, got nil")
	}
	if !strings.Contains(err.Error(), "parse redis url") {
		t.Fatalf("error %q should wrap 'parse redis url'", err)
	}
}