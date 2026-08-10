package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestReconcileC5ZeroBroadcastArtifact(t *testing.T) {
	var methods []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			ID     int    `json:"id"`
			Method string `json:"method"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		methods = append(methods, request.Method)
		json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": request.ID, "result": "0x2105"})
	}))
	defer server.Close()

	path := filepath.Join(t.TempDir(), "c5.json")
	if err := os.WriteFile(path, []byte(`{"stage":"C5_OPEN_DRY_RUN","chain_id":8453,"signed":false,"broadcast_count":0,"transaction_hashes":[]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	report, err := reconcile(context.Background(), path, &rpcClient{url: server.URL, client: server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	if report.Verdict != "PASS" || report.LedgerHashCount != 0 || report.ObservedChainID != 8453 || !report.ReadOnly {
		t.Fatalf("unexpected report: %+v", report)
	}
	if len(methods) != 1 || methods[0] != "eth_chainId" {
		t.Fatalf("unexpected methods: %v", methods)
	}
}

func TestRPCClientRejectsMutatingMethodBeforeNetwork(t *testing.T) {
	client := &rpcClient{url: "http://127.0.0.1:1", client: &http.Client{Timeout: time.Millisecond}}
	var result string
	if err := client.call(context.Background(), "eth_sendRawTransaction", []any{"0x"}, &result); err == nil {
		t.Fatal("mutating method must be rejected")
	}
}

func TestReconcileRejectsLedgerCountMismatch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": 1, "result": "0x2105"})
	}))
	defer server.Close()
	path := filepath.Join(t.TempDir(), "bad.json")
	payload := `{"stage":"test","chain_id":8453,"signed":true,"broadcast_count":1,"transaction_hashes":[]}`
	os.WriteFile(path, []byte(payload), 0o600)
	report, err := reconcile(context.Background(), path, &rpcClient{url: server.URL, client: server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	if report.Verdict != "FAIL" {
		t.Fatalf("expected FAIL, got %+v", report)
	}
}

func TestReconcileExecutorJSONLLedger(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": 1, "result": "0x2105"})
	}))
	defer server.Close()
	path := filepath.Join(t.TempDir(), "ledger.jsonl")
	rows := []byte("{\"event\":\"kill_switch\",\"state\":\"EXIT_ONLY\"}\n")
	if err := os.WriteFile(path, rows, 0o600); err != nil {
		t.Fatal(err)
	}
	report, err := reconcileLedger(context.Background(), path, 8453, &rpcClient{url: server.URL, client: server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	if report.Verdict != "PASS" || report.Stage != "EXECUTION_LEDGER" || report.LedgerHashCount != 0 {
		t.Fatalf("unexpected ledger report: %+v", report)
	}
}
