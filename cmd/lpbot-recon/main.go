// lpbot-recon performs read-only ledger/artifact to Base receipt reconciliation.
package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const Version = "0.1.0-readonly"

type artifact struct {
	Stage             string   `json:"stage"`
	ChainID           int64    `json:"chain_id"`
	Signed            bool     `json:"signed"`
	BroadcastCount    int      `json:"broadcast_count"`
	TransactionHashes []string `json:"transaction_hashes"`
}

type receiptObservation struct {
	TxHash      string `json:"tx_hash"`
	Found       bool   `json:"found"`
	Status      string `json:"status,omitempty"`
	BlockNumber string `json:"block_number,omitempty"`
}

type reconcileReport struct {
	GeneratedAt     string               `json:"generated_at"`
	Verdict         string               `json:"verdict"`
	Artifact        string               `json:"artifact"`
	Stage           string               `json:"stage"`
	ExpectedChainID int64                `json:"expected_chain_id"`
	ObservedChainID int64                `json:"observed_chain_id"`
	LedgerHashCount int                  `json:"ledger_hash_count"`
	BroadcastCount  int                  `json:"broadcast_count"`
	Signed          bool                 `json:"signed"`
	ReadOnly        bool                 `json:"read_only"`
	RPCMethods      []string             `json:"rpc_methods"`
	Receipts        []receiptObservation `json:"receipts"`
	Errors          []string             `json:"errors"`
}

type rpcClient struct {
	url    string
	client *http.Client
	nextID int
}

func (r *rpcClient) call(ctx context.Context, method string, params any, result any) error {
	// Keep the operator CLI structurally read-only.  Adding a mutating method
	// requires an explicit code change rather than an arbitrary CLI flag.
	if method != "eth_chainId" && method != "eth_getTransactionReceipt" {
		return fmt.Errorf("RPC method %q is not in the read-only allowlist", method)
	}
	r.nextID++
	body, err := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": r.nextID, "method": method, "params": params})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, r.url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "lpbot-recon/0.1-readonly")
	resp, err := r.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("RPC HTTP status %d", resp.StatusCode)
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
		Error  *struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&envelope); err != nil {
		return err
	}
	if envelope.Error != nil {
		return fmt.Errorf("RPC %s failed (%d): %s", method, envelope.Error.Code, envelope.Error.Message)
	}
	return json.Unmarshal(envelope.Result, result)
}

func reconcile(ctx context.Context, artifactPath string, rpc *rpcClient) (reconcileReport, error) {
	data, err := os.ReadFile(artifactPath)
	if err != nil {
		return reconcileReport{}, err
	}
	var a artifact
	if err := json.Unmarshal(data, &a); err != nil {
		return reconcileReport{}, err
	}
	return reconcileLoaded(ctx, artifactPath, a, rpc)
}

func reconcileLedger(ctx context.Context, ledgerPath string, chainID int64, rpc *rpcClient) (reconcileReport, error) {
	file, err := os.Open(ledgerPath)
	if err != nil {
		return reconcileReport{}, err
	}
	defer file.Close()
	seen := make(map[string]bool)
	var hashes []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		if strings.TrimSpace(scanner.Text()) == "" {
			continue
		}
		var row struct {
			TxHash string `json:"tx_hash"`
		}
		if err := json.Unmarshal(scanner.Bytes(), &row); err != nil {
			return reconcileReport{}, fmt.Errorf("invalid ledger JSONL: %w", err)
		}
		if row.TxHash != "" && !seen[strings.ToLower(row.TxHash)] {
			seen[strings.ToLower(row.TxHash)] = true
			hashes = append(hashes, row.TxHash)
		}
	}
	if err := scanner.Err(); err != nil {
		return reconcileReport{}, err
	}
	return reconcileLoaded(ctx, ledgerPath, artifact{
		Stage: "EXECUTION_LEDGER", ChainID: chainID, Signed: len(hashes) > 0,
		BroadcastCount: len(hashes), TransactionHashes: hashes,
	}, rpc)
}

func reconcileLoaded(ctx context.Context, artifactPath string, a artifact, rpc *rpcClient) (reconcileReport, error) {
	report := reconcileReport{
		GeneratedAt: time.Now().UTC().Format(time.RFC3339Nano), Artifact: artifactPath,
		Stage: a.Stage, ExpectedChainID: a.ChainID, LedgerHashCount: len(a.TransactionHashes),
		BroadcastCount: a.BroadcastCount, Signed: a.Signed, ReadOnly: true,
		RPCMethods: []string{"eth_chainId", "eth_getTransactionReceipt"},
		Receipts:   []receiptObservation{}, Errors: []string{},
	}
	var chainHex string
	if err := rpc.call(ctx, "eth_chainId", []any{}, &chainHex); err != nil {
		return report, err
	}
	observedChainID, err := strconv.ParseInt(strings.TrimPrefix(chainHex, "0x"), 16, 64)
	if err != nil {
		return report, fmt.Errorf("invalid eth_chainId %q: %w", chainHex, err)
	}
	report.ObservedChainID = observedChainID
	if report.ExpectedChainID != report.ObservedChainID {
		report.Errors = append(report.Errors, "artifact chain_id does not match RPC")
	}
	if a.BroadcastCount != len(a.TransactionHashes) {
		report.Errors = append(report.Errors, "broadcast_count does not equal transaction_hashes length")
	}
	if !a.Signed && len(a.TransactionHashes) != 0 {
		report.Errors = append(report.Errors, "unsigned artifact contains transaction hashes")
	}
	for _, hash := range a.TransactionHashes {
		if !validTxHash(hash) {
			report.Errors = append(report.Errors, "malformed transaction hash: "+hash)
			continue
		}
		var receipt *struct {
			Status      string `json:"status"`
			BlockNumber string `json:"blockNumber"`
		}
		if err := rpc.call(ctx, "eth_getTransactionReceipt", []any{hash}, &receipt); err != nil {
			return report, err
		}
		observation := receiptObservation{TxHash: hash, Found: receipt != nil}
		if receipt != nil {
			observation.Status, observation.BlockNumber = receipt.Status, receipt.BlockNumber
		} else {
			report.Errors = append(report.Errors, "transaction receipt not found: "+hash)
		}
		report.Receipts = append(report.Receipts, observation)
	}
	if len(report.Errors) == 0 {
		report.Verdict = "PASS"
	} else {
		report.Verdict = "FAIL"
	}
	return report, nil
}

func validTxHash(value string) bool {
	if len(value) != 66 || !strings.HasPrefix(value, "0x") {
		return false
	}
	_, err := strconv.ParseUint(value[2:18], 16, 64)
	if err != nil {
		return false
	}
	for _, character := range value[18:] {
		if !strings.ContainsRune("0123456789abcdefABCDEF", character) {
			return false
		}
	}
	return true
}

func main() {
	artifactPath := flag.String("artifact", "", "C5/execution JSON artifact to reconcile")
	ledgerPath := flag.String("ledger", "", "executor JSONL ledger to reconcile")
	ledgerChainID := flag.Int64("chain-id", 8453, "expected chain id for --ledger")
	rpcURL := flag.String("rpc-url", envOr("BASE_RPC_URL", "https://mainnet.base.org"), "Base JSON-RPC endpoint")
	output := flag.String("output", "", "optional JSON report path")
	version := flag.Bool("version", false, "print version")
	timeout := flag.Duration("timeout", 30*time.Second, "read-only RPC timeout")
	flag.Parse()
	if *version {
		fmt.Println(Version)
		return
	}
	if (*artifactPath == "") == (*ledgerPath == "") {
		fmt.Fprintln(os.Stderr, "exactly one of --artifact or --ledger is required")
		os.Exit(2)
	}
	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()
	rpc := &rpcClient{url: *rpcURL, client: &http.Client{Timeout: *timeout}}
	var report reconcileReport
	var err error
	if *artifactPath != "" {
		report, err = reconcile(ctx, *artifactPath, rpc)
	} else {
		report, err = reconcileLedger(ctx, *ledgerPath, *ledgerChainID, rpc)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		panic(err)
	}
	encoded = append(encoded, '\n')
	if *output != "" {
		if err := os.MkdirAll(filepath.Dir(*output), 0o755); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if err := os.WriteFile(*output, encoded, 0o644); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	os.Stdout.Write(encoded) // operator-visible report; contains no wallet secret
	if report.Verdict != "PASS" {
		os.Exit(3)
	}
}

func envOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
