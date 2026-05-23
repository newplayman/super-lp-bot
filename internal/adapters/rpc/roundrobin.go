// Package rpc provides a round-robin RPC client with automatic failover.
package rpc

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/big"
	"net/http"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/ethclient"

	"github.com/lpbot/lpbot/internal/domain"
)

const (
	defaultHealthCheckInterval = 30 * time.Second
	defaultHealthCheckTimeout  = 2 * time.Second
	switchLogCooldown          = 15 * time.Second
	endpointFailureCooldown    = 45 * time.Second
	endpointRateLimitCooldown  = 2 * time.Minute
	callContractCacheTTL       = 20 * time.Second
	callContractCacheMaxItems  = 2048
)

// Default public RPC endpoints
var (
	// Base mainnet endpoints
	BaseEndpoints = []string{
		"https://mainnet.base.org",
		"https://mainnet-preconf.base.org",
	}

	// Extra public Base endpoints for failover and latency-based ordering.
	BasePublicEndpoints = []string{
		"https://base.drpc.org",
	}

	// Base Sepolia testnet endpoints
	BaseSepoliaEndpoints = []string{
		"https://sepolia.base.org",
		"https://sepolia-preconf.base.org",
	}

	// Ethereum mainnet endpoints
	EthEndpoints = []string{
		"https://eth.llamarpc.com",
		"https://rpc.ankr.com/eth",
	}

	// Solana mainnet endpoints
	SolanaEndpoints = []string{
		"https://api.mainnet.solana.com",
	}

	// Extra public Solana endpoints.
	SolanaPublicEndpoints = []string{
		"https://api.mainnet-beta.solana.com",
	}
)

type endpointProbeResult struct {
	endpoint string
	latency  time.Duration
	index    int
	ok       bool
	errMsg   string
}

type switchLogState struct {
	lastAt     time.Time
	suppressed int
}

type callCacheEntry struct {
	value     []byte
	expiresAt time.Time
}

var (
	switchLogStateMu sync.Mutex
	switchLogStates  = make(map[string]switchLogState)
	endpointStateMu  sync.Mutex
	endpointCooldown = make(map[string]time.Time)
)

// RoundRobinProvider distributes requests across multiple RPC endpoints with automatic failover.
type RoundRobinProvider struct {
	chainID        domain.ChainID
	client         *ethclient.Client
	mu             sync.RWMutex
	endpoints      []string
	current        uint32 // atomic index
	httpClient     *http.Client
	stopCh         chan struct{}
	closed         uint32
	healthInterval time.Duration
	healthTimeout  time.Duration
	callCacheMu    sync.Mutex
	callCache      map[string]callCacheEntry
}

// Config holds the configuration for a round-robin RPC provider.
type Config struct {
	ChainID    domain.ChainID
	Endpoints  []string
	HTTPClient *http.Client
	// HealthCheckInterval controls how often endpoints are re-probed and re-ordered.
	HealthCheckInterval time.Duration
	// HealthCheckTimeout controls per-endpoint probe timeout.
	HealthCheckTimeout time.Duration
}

// NewRoundRobinProvider creates a new round-robin RPC provider.
func NewRoundRobinProvider(cfg Config) (*RoundRobinProvider, error) {
	if len(cfg.Endpoints) == 0 {
		return nil, fmt.Errorf("at least one RPC endpoint is required")
	}

	cleanEndpoints := normalizeEndpoints(cfg.Endpoints)
	if len(cleanEndpoints) == 0 {
		return nil, fmt.Errorf("no usable RPC endpoint configured")
	}

	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultHealthCheckTimeout}
	}

	healthInterval := cfg.HealthCheckInterval
	if healthInterval <= 0 {
		healthInterval = defaultHealthCheckInterval
	}
	healthTimeout := cfg.HealthCheckTimeout
	if healthTimeout <= 0 {
		healthTimeout = defaultHealthCheckTimeout
	}

	p := &RoundRobinProvider{
		chainID:        cfg.ChainID,
		endpoints:      cleanEndpoints,
		httpClient:     httpClient,
		stopCh:         make(chan struct{}),
		healthInterval: healthInterval,
		healthTimeout:  healthTimeout,
		callCache:      make(map[string]callCacheEntry),
	}

	ranked, healthSummary := rankEndpointsByLatency(
		context.Background(),
		p.endpoints,
		p.httpClient,
		p.healthTimeout,
	)
	ranked = p.prioritizeAvailableEndpoints(ranked)
	p.endpoints = ranked
	log.Printf("[rpc:%s] initial rpc order: %v", p.chainID, p.endpoints)
	if healthSummary != "" {
		log.Printf("[rpc:%s] initial health check summary: %s", p.chainID, healthSummary)
	}

	if err := p.connectAtLeastOne(); err != nil {
		return nil, err
	}

	go p.healthLoop()

	return p, nil
}

func (p *RoundRobinProvider) healthLoop() {
	ticker := time.NewTicker(p.healthInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if len(p.copyEndpoints()) == 0 {
				continue
			}
			ranked, healthSummary := rankEndpointsByLatency(
				context.Background(),
				p.copyEndpoints(),
				p.httpClient,
				p.healthTimeout,
			)
			if len(ranked) == 0 {
				continue
			}
			ranked = p.prioritizeAvailableEndpoints(ranked)

			p.mu.Lock()
			prevPrimary := ""
			if len(p.endpoints) > 0 {
				prevPrimary = p.endpoints[0]
			}
			p.endpoints = ranked
			p.mu.Unlock()

			if healthSummary != "" {
				log.Printf("[rpc:%s] health check summary: %s", p.chainID, healthSummary)
			}
			newPrimary := ranked[0]
			if prevPrimary != "" && prevPrimary != newPrimary {
				log.Printf("[rpc:%s] primary rpc changed: %s -> %s", p.chainID, prevPrimary, newPrimary)
			}
		case <-p.stopCh:
			return
		}
	}
}

// NewBaseProvider creates a provider for Base mainnet with default endpoints.
func NewBaseProvider() (*RoundRobinProvider, error) {
	return NewRoundRobinProvider(Config{
		ChainID:   domain.ChainBase,
		Endpoints: BaseEndpoints,
	})
}

// NewBaseSepoliaProvider creates a provider for Base Sepolia testnet.
func NewBaseSepoliaProvider() (*RoundRobinProvider, error) {
	return NewRoundRobinProvider(Config{
		ChainID:   "base-sepolia",
		Endpoints: BaseSepoliaEndpoints,
	})
}

// ChainID returns the chain ID.
func (p *RoundRobinProvider) ChainID() domain.ChainID {
	return p.chainID
}

// Client returns the current ethclient.
func (p *RoundRobinProvider) Client() *ethclient.Client {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.client
}

// Close stops background health checks and closes the current client.
func (p *RoundRobinProvider) Close() error {
	if p == nil {
		return nil
	}
	if !atomic.CompareAndSwapUint32(&p.closed, 0, 1) {
		return nil
	}

	close(p.stopCh)

	p.mu.Lock()
	client := p.client
	p.client = nil
	p.mu.Unlock()

	if client != nil {
		client.Close()
	}

	return nil
}

// Endpoint returns the current endpoint URL.
func (p *RoundRobinProvider) Endpoint() string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	if len(p.endpoints) == 0 {
		return ""
	}
	idx := atomic.LoadUint32(&p.current) % uint32(len(p.endpoints))
	return p.endpoints[idx]
}

// nextEndpoint rotates to the next endpoint in the list.
func (p *RoundRobinProvider) nextEndpoint() error {
	endpoints := p.copyEndpoints()
	if len(endpoints) == 0 {
		return fmt.Errorf("no rpc endpoint configured")
	}

	prevIdx := int(atomic.LoadUint32(&p.current) % uint32(len(endpoints)))
	prev := endpoints[prevIdx]
	p.markEndpointCooldown(prev)

	startIdx := prevIdx
	lastErr := error(nil)
	cooledSkipped := 0

	for pass := 0; pass < 2; pass++ {
		allowCooled := pass == 1 && cooledSkipped == len(endpoints)-1
		for step := 1; step <= len(endpoints); step++ {
			idx := (startIdx + step) % len(endpoints)
			endpoint := endpoints[idx]
			if endpoint == prev {
				continue
			}
			if !allowCooled && p.isEndpointCooling(endpoint) {
				cooledSkipped++
				continue
			}

			client, err := p.connect(endpoint)
			if err != nil {
				p.markEndpointCooldown(endpoint)
				lastErr = fmt.Errorf("failed to connect to endpoint %s: %w", endpoint, err)
				continue
			}

			atomic.StoreUint32(&p.current, uint32(idx))
			p.mu.Lock()
			p.client = client
			p.mu.Unlock()
			p.logEndpointSwitch(prev, endpoint)
			return nil
		}
	}

	if lastErr != nil {
		return lastErr
	}
	return fmt.Errorf("no alternate rpc endpoint available after cooldown")
}

func (p *RoundRobinProvider) logEndpointSwitch(prev, endpoint string) {
	if prev == "" || endpoint == "" || prev == endpoint {
		return
	}

	now := time.Now()
	key := string(p.chainID)

	switchLogStateMu.Lock()
	state := switchLogStates[key]
	if !state.lastAt.IsZero() && now.Sub(state.lastAt) < switchLogCooldown {
		state.suppressed++
		switchLogStates[key] = state
		switchLogStateMu.Unlock()
		return
	}

	suppressed := state.suppressed
	state.suppressed = 0
	state.lastAt = now
	switchLogStates[key] = state
	switchLogStateMu.Unlock()

	if suppressed > 0 {
		log.Printf("[rpc:%s] switched rpc endpoint: %s -> %s (suppressed %d rapid switches)", p.chainID, prev, endpoint, suppressed)
		return
	}
	log.Printf("[rpc:%s] switched rpc endpoint: %s -> %s", p.chainID, prev, endpoint)
}

func (p *RoundRobinProvider) markEndpointCooldown(endpoint string) {
	p.markEndpointCooldownUntil(endpoint, time.Now().Add(endpointFailureCooldown))
}

func (p *RoundRobinProvider) markEndpointRateLimited(endpoint string) {
	until := time.Now().Add(endpointRateLimitCooldown)
	p.markEndpointCooldownUntil(endpoint, until)
	if endpoint != "" {
		log.Printf("[rpc:%s] rate limited endpoint cooling down until %s: %s", p.chainID, until.Format(time.RFC3339), endpoint)
	}
}

func (p *RoundRobinProvider) markCurrentEndpointRateLimited() {
	p.markEndpointRateLimited(p.Endpoint())
}

func (p *RoundRobinProvider) markEndpointCooldownUntil(endpoint string, until time.Time) {
	if endpoint == "" {
		return
	}
	key := string(p.chainID) + "|" + endpoint
	endpointStateMu.Lock()
	if existing, ok := endpointCooldown[key]; !ok || existing.Before(until) {
		endpointCooldown[key] = until
	}
	endpointStateMu.Unlock()
}

func (p *RoundRobinProvider) isEndpointCooling(endpoint string) bool {
	if endpoint == "" {
		return false
	}
	key := string(p.chainID) + "|" + endpoint
	now := time.Now()
	endpointStateMu.Lock()
	defer endpointStateMu.Unlock()
	until, ok := endpointCooldown[key]
	if !ok {
		return false
	}
	if !until.After(now) {
		delete(endpointCooldown, key)
		return false
	}
	return true
}

func (p *RoundRobinProvider) prioritizeAvailableEndpoints(endpoints []string) []string {
	if len(endpoints) <= 1 {
		return endpoints
	}

	available := make([]string, 0, len(endpoints))
	cooling := make([]string, 0, len(endpoints))
	for _, endpoint := range endpoints {
		if p.isEndpointCooling(endpoint) {
			cooling = append(cooling, endpoint)
			continue
		}
		available = append(available, endpoint)
	}

	if len(available) == 0 || len(cooling) == 0 {
		return endpoints
	}

	return append(available, cooling...)
}

func isRateLimitError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "429") ||
		strings.Contains(msg, "too many request") ||
		strings.Contains(msg, "rate limit") ||
		strings.Contains(msg, "over rate limit")
}

func (p *RoundRobinProvider) shouldStopAfterRPCError(err error) bool {
	if !isRateLimitError(err) {
		return false
	}
	p.markCurrentEndpointRateLimited()
	_ = p.nextEndpoint()
	return true
}

func (p *RoundRobinProvider) retryAfterRateLimit(err error) (bool, error) {
	if !isRateLimitError(err) {
		return false, nil
	}
	p.markCurrentEndpointRateLimited()
	if rotateErr := p.nextEndpoint(); rotateErr != nil {
		return true, rotateErr
	}
	return true, nil
}

func cloneBytes(value []byte) []byte {
	if value == nil {
		return nil
	}
	dst := make([]byte, len(value))
	copy(dst, value)
	return dst
}

func (p *RoundRobinProvider) callContractCacheKey(msg ethereum.CallMsg, blockNumber *big.Int) (string, bool) {
	if msg.To == nil || len(msg.Data) == 0 {
		return "", false
	}
	if msg.From != (common.Address{}) || msg.Gas != 0 || msg.Value != nil || msg.GasPrice != nil {
		return "", false
	}

	blockKey := "latest"
	if blockNumber != nil {
		blockKey = blockNumber.String()
	}

	return fmt.Sprintf("%s|%s|%s|%s", p.chainID, msg.To.Hex(), common.Bytes2Hex(msg.Data), blockKey), true
}

func (p *RoundRobinProvider) getCallContractCache(key string) ([]byte, bool) {
	now := time.Now()
	p.callCacheMu.Lock()
	defer p.callCacheMu.Unlock()

	entry, ok := p.callCache[key]
	if !ok {
		return nil, false
	}
	if !entry.expiresAt.After(now) {
		delete(p.callCache, key)
		return nil, false
	}
	return cloneBytes(entry.value), true
}

func (p *RoundRobinProvider) setCallContractCache(key string, value []byte) {
	now := time.Now()
	p.callCacheMu.Lock()
	defer p.callCacheMu.Unlock()

	if len(p.callCache) >= callContractCacheMaxItems {
		for k, entry := range p.callCache {
			if !entry.expiresAt.After(now) {
				delete(p.callCache, k)
			}
		}
		if len(p.callCache) >= callContractCacheMaxItems {
			p.callCache = make(map[string]callCacheEntry)
		}
	}

	p.callCache[key] = callCacheEntry{
		value:     cloneBytes(value),
		expiresAt: now.Add(callContractCacheTTL),
	}
}

// getClientWithRetry gets a client, rotating on failure.
func (p *RoundRobinProvider) getClientWithRetry() (*ethclient.Client, error) {
	p.mu.RLock()
	client := p.client
	p.mu.RUnlock()

	if client != nil {
		return client, nil
	}

	if err := p.connectAtLeastOne(); err != nil {
		return nil, err
	}

	p.mu.RLock()
	client = p.client
	p.mu.RUnlock()
	return client, nil
}

func (p *RoundRobinProvider) connect(endpoint string) (*ethclient.Client, error) {
	client, err := ethclient.Dial(endpoint)
	if err != nil {
		return nil, err
	}

	return client, nil
}

func (p *RoundRobinProvider) connectAtLeastOne() error {
	endpoints := p.copyEndpoints()
	current := p.Endpoint()
	for idx, endpoint := range endpoints {
		client, err := p.connect(endpoint)
		if err != nil {
			continue
		}
		p.mu.Lock()
		p.client = client
		p.mu.Unlock()
		atomic.StoreUint32(&p.current, uint32(idx))
		if current == "" {
			log.Printf("[rpc:%s] rpc initialized at: %s", p.chainID, endpoint)
		} else if current != endpoint {
			log.Printf("[rpc:%s] rpc reconnect: %s -> %s", p.chainID, current, endpoint)
		}
		return nil
	}

	return fmt.Errorf("failed to connect to all configured RPC endpoints")
}

func (p *RoundRobinProvider) copyEndpoints() []string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	dst := make([]string, len(p.endpoints))
	copy(dst, p.endpoints)
	return dst
}

func normalizeEndpoints(endpoints []string) []string {
	seen := make(map[string]struct{})
	normalized := make([]string, 0, len(endpoints))

	for _, endpoint := range endpoints {
		parts := strings.Split(endpoint, ",")
		for _, part := range parts {
			value := strings.TrimSpace(part)
			if value == "" {
				continue
			}
			value = strings.TrimSuffix(value, "/")
			value = strings.TrimSpace(value)
			if !strings.HasPrefix(value, "http://") && !strings.HasPrefix(value, "https://") {
				continue
			}
			if _, exists := seen[value]; exists {
				continue
			}
			seen[value] = struct{}{}
			normalized = append(normalized, value)
		}
	}

	return normalized
}

func isReserveEndpoint(endpoint string) bool {
	value := strings.ToLower(strings.TrimSpace(endpoint))
	return strings.Contains(value, ".quiknode.pro/") || strings.Contains(value, ".quiknode.pro")
}

func rankEndpointsByLatency(ctx context.Context, endpoints []string, httpClient *http.Client, timeout time.Duration) ([]string, string) {
	if len(endpoints) <= 1 {
		return endpoints, ""
	}

	results := make(chan endpointProbeResult, len(endpoints))
	var wg sync.WaitGroup
	wg.Add(len(endpoints))

	for idx, endpoint := range endpoints {
		go func(i int, endpoint string) {
			defer wg.Done()
			latency, err := probeEndpointLatency(ctx, endpoint, httpClient, timeout)
			errMsg := ""
			if err != nil {
				errMsg = err.Error()
			}
			results <- endpointProbeResult{
				endpoint: endpoint,
				latency:  latency,
				index:    i,
				ok:       err == nil,
				errMsg:   errMsg,
			}
		}(idx, endpoint)
	}

	wg.Wait()
	close(results)

	probeResults := make([]endpointProbeResult, 0, len(endpoints))
	allFailed := true
	for r := range results {
		if r.ok {
			allFailed = false
		}
		probeResults = append(probeResults, r)
	}

	if allFailed {
		failSummary := make([]string, 0, len(probeResults))
		for _, result := range probeResults {
			failSummary = append(failSummary, fmt.Sprintf("%s:FAIL(%s)", result.endpoint, result.errMsg))
		}
		return endpoints, strings.Join(failSummary, ", ")
	}

	sort.SliceStable(probeResults, func(i, j int) bool {
		if probeResults[i].ok != probeResults[j].ok {
			return probeResults[i].ok
		}

		leftReserve := isReserveEndpoint(probeResults[i].endpoint)
		rightReserve := isReserveEndpoint(probeResults[j].endpoint)
		if leftReserve != rightReserve {
			return !leftReserve
		}

		if probeResults[i].ok && probeResults[i].latency != probeResults[j].latency {
			return probeResults[i].latency < probeResults[j].latency
		}

		return probeResults[i].index < probeResults[j].index
	})

	ranked := make([]string, 0, len(probeResults))
	summaryParts := make([]string, 0, len(probeResults))
	for _, result := range probeResults {
		ranked = append(ranked, result.endpoint)
		if result.ok {
			summaryParts = append(summaryParts, fmt.Sprintf("%s:OK(%s)", result.endpoint, result.latency))
		} else {
			summaryParts = append(summaryParts, fmt.Sprintf("%s:FAIL(%s)", result.endpoint, result.errMsg))
		}
	}
	return ranked, strings.Join(summaryParts, ", ")
}

func probeEndpointLatency(ctx context.Context, endpoint string, httpClient *http.Client, timeout time.Duration) (time.Duration, error) {
	if timeout <= 0 {
		timeout = defaultHealthCheckTimeout
	}

	body := []byte(`{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}`)
	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return 0, err
	}

	req.Header.Set("Content-Type", "application/json")
	start := time.Now()
	resp, err := httpClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return 0, fmt.Errorf("unexpected status: %s", resp.Status)
	}

	var payload struct {
		Error  interface{} `json:"error"`
		Result interface{} `json:"result"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 8*1024)).Decode(&payload); err != nil {
		return 0, err
	}

	if payload.Error != nil {
		return 0, fmt.Errorf("rpc error: %v", payload.Error)
	}
	if payload.Result == nil {
		return 0, fmt.Errorf("rpc result empty")
	}

	return time.Since(start), nil
}

// BalanceAt returns the balance at the given block.
func (p *RoundRobinProvider) BalanceAt(ctx context.Context, addr domain.Address, block *big.Int) (*big.Int, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		balance, err := client.BalanceAt(ctx, common.HexToAddress(addr.String()), block)
		if err == nil {
			return balance, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// NonceAt returns the nonce at the given block.
func (p *RoundRobinProvider) NonceAt(ctx context.Context, addr domain.Address, block *big.Int) (uint64, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return 0, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return 0, err
		}
		nonce, err := client.NonceAt(ctx, common.HexToAddress(addr.String()), block)
		if err == nil {
			return nonce, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return 0, err
		}
		if err := p.nextEndpoint(); err != nil {
			return 0, lastErr
		}
	}
	return 0, lastErr
}

// PendingNonceAt returns the pending nonce for the given address.
// This is a convenience method for the RPCProvider interface.
func (p *RoundRobinProvider) PendingNonceAt(ctx context.Context, addr domain.Address) (uint64, error) {
	// nil block means pending
	return p.NonceAt(ctx, addr, nil)
}

// BlockByHash returns the block with the given hash.
func (p *RoundRobinProvider) BlockByHash(ctx context.Context, hash common.Hash) (*types.Block, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		block, err := client.BlockByHash(ctx, hash)
		if err == nil {
			return block, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// BlockByNumber returns the block with the given number.
func (p *RoundRobinProvider) BlockByNumber(ctx context.Context, num *big.Int) (*types.Block, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		block, err := client.BlockByNumber(ctx, num)
		if err == nil {
			return block, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// HeaderByHash returns the header with the given hash.
func (p *RoundRobinProvider) HeaderByHash(ctx context.Context, hash common.Hash) (*types.Header, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		header, err := client.HeaderByHash(ctx, hash)
		if err == nil {
			return header, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// HeaderByNumber returns the header with the given number.
func (p *RoundRobinProvider) HeaderByNumber(ctx context.Context, num *big.Int) (*types.Header, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		header, err := client.HeaderByNumber(ctx, num)
		if err == nil {
			return header, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// SuggestGasPrice suggests a gas price based on the current network conditions.
func (p *RoundRobinProvider) SuggestGasPrice(ctx context.Context) (*big.Int, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		price, err := client.SuggestGasPrice(ctx)
		if err == nil {
			return price, nil
		}
		lastErr = err
		if retry, rotateErr := p.retryAfterRateLimit(err); retry {
			if rotateErr != nil {
				return nil, lastErr
			}
			continue
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// SuggestGasTipCap suggests a gas tip cap based on the current network conditions.
func (p *RoundRobinProvider) SuggestGasTipCap(ctx context.Context) (*big.Int, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		tip, err := client.SuggestGasTipCap(ctx)
		if err == nil {
			return tip, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// EstimateGas estimates the gas needed for a transaction.
func (p *RoundRobinProvider) EstimateGas(ctx context.Context, msg ethereum.CallMsg) (uint64, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return 0, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return 0, err
		}
		gas, err := client.EstimateGas(ctx, msg)
		if err == nil {
			return gas, nil
		}
		lastErr = err
		if retry, rotateErr := p.retryAfterRateLimit(err); retry {
			if rotateErr != nil {
				return 0, lastErr
			}
			continue
		}
		if err := p.nextEndpoint(); err != nil {
			return 0, lastErr
		}
	}
	return 0, lastErr
}

// CodeAt returns the code at the given address.
func (p *RoundRobinProvider) CodeAt(ctx context.Context, addr domain.Address, block *big.Int) ([]byte, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		code, err := client.CodeAt(ctx, common.HexToAddress(addr.String()), block)
		if err == nil {
			return code, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// PendingCodeAt returns the pending code at the given address.
func (p *RoundRobinProvider) PendingCodeAt(ctx context.Context, addr domain.Address) ([]byte, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		code, err := client.PendingCodeAt(ctx, common.HexToAddress(addr.String()))
		if err == nil {
			return code, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// CallContract executes a message call.
func (p *RoundRobinProvider) CallContract(ctx context.Context, msg ethereum.CallMsg, blockNumber *big.Int) ([]byte, error) {
	cacheKey, cacheable := p.callContractCacheKey(msg, blockNumber)
	if cacheable {
		if cached, ok := p.getCallContractCache(cacheKey); ok {
			return cached, nil
		}
	}

	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		result, err := client.CallContract(ctx, msg, blockNumber)
		if err == nil {
			if cacheable {
				p.setCallContractCache(cacheKey, result)
			}
			return result, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

func (p *RoundRobinProvider) retryAttempts() int {
	attempts := len(p.copyEndpoints())
	if attempts <= 0 {
		return 1
	}
	return attempts
}

// FilterLogs executes a log filter query.
func (p *RoundRobinProvider) FilterLogs(ctx context.Context, q ethereum.FilterQuery) ([]types.Log, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		logs, err := client.FilterLogs(ctx, q)
		if err == nil {
			return logs, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// SendTransaction sends a signed transaction.
func (p *RoundRobinProvider) SendTransaction(ctx context.Context, tx *types.Transaction) error {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return err
		}
		err = client.SendTransaction(ctx, tx)
		if err == nil {
			return nil
		}
		lastErr = err
		if strings.Contains(err.Error(), "already known") || strings.Contains(err.Error(), "replacement underpriced") {
			return err // Don't retry for these errors
		}
		if p.shouldStopAfterRPCError(err) {
			return err
		}
		if err := p.nextEndpoint(); err != nil {
			return lastErr
		}
	}
	return lastErr
}

// TransactionByHash returns the transaction with the given hash.
func (p *RoundRobinProvider) TransactionByHash(ctx context.Context, hash common.Hash) (*types.Transaction, bool, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, false, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, false, err
		}
		tx, pending, err := client.TransactionByHash(ctx, hash)
		if err == nil {
			return tx, pending, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, false, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, false, lastErr
		}
	}
	return nil, false, lastErr
}

// TransactionReceipt returns the receipt for the given transaction hash.
func (p *RoundRobinProvider) TransactionReceipt(ctx context.Context, hash common.Hash) (*types.Receipt, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		receipt, err := client.TransactionReceipt(ctx, hash)
		if err == nil {
			return receipt, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}

// NetworkID returns the network ID.
func (p *RoundRobinProvider) NetworkID(ctx context.Context) (*big.Int, error) {
	var lastErr error
	for attempt := 0; attempt < p.retryAttempts(); attempt++ {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		client, err := p.getClientWithRetry()
		if err != nil {
			return nil, err
		}
		id, err := client.NetworkID(ctx)
		if err == nil {
			return id, nil
		}
		lastErr = err
		if p.shouldStopAfterRPCError(err) {
			return nil, err
		}
		if err := p.nextEndpoint(); err != nil {
			return nil, lastErr
		}
	}
	return nil, lastErr
}
