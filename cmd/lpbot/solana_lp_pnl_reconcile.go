package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"

	solanago "github.com/gagliardetto/solana-go"
	solrpc "github.com/gagliardetto/solana-go/rpc"
	"github.com/lpbot/lpbot/internal/adapters/store/postgres"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
)

type solanaLPRealizedPnLReport struct {
	PositionID     string
	OpenTxHash     string
	DecreaseTxHash string
	CloseTxHash    string
	SOLPriceUSDC   domain.Decimal
	PrincipalUSD   domain.Decimal
	ExitUSDC       domain.Decimal
	ExitSOL        domain.Decimal
	ExitValueUSD   domain.Decimal
	GasUSD         domain.Decimal
	NetPnLUSD      domain.Decimal
	LedgerEntries  int
}

type solanaLPRealizedStore interface {
	DB() *sql.DB
	Append(context.Context, ports.LedgerEntry) (ports.LedgerEntry, error)
}

func runSolanaLPRealizedPnLReconcile(ctx context.Context, cfg *config.Config, positionID string, slippageBPS int) error {
	if cfg == nil || strings.TrimSpace(cfg.Store.PostgresDSN) == "" {
		return fmt.Errorf("postgres dsn is required for solana lp realized pnl reconcile")
	}
	store, err := postgres.NewFromDSN(strings.TrimSpace(cfg.Store.PostgresDSN))
	if err != nil {
		return fmt.Errorf("open postgres for solana lp realized pnl reconcile: %w", err)
	}
	defer store.Close()

	pos, err := resolveSolanaLPReconcilePosition(ctx, store.DB(), positionID)
	if err != nil {
		return err
	}
	decreaseTx, closeTx, err := findSolanaLPExitTxHashes(ctx, store.DB(), pos.ID)
	if err != nil {
		return err
	}
	wallet, err := resolveSolanaLPReconcileWallet(ctx, store.DB(), pos.ID)
	if err != nil {
		return err
	}
	report, err := reconcileSolanaLPRealizedPnL(ctx, cfg, store, pos, wallet, decreaseTx, closeTx, slippageBPS)
	if err != nil {
		return err
	}
	fmt.Printf("solana_lp_realized_pnl_reconciled position_id=%s open_tx=%s decrease_tx=%s close_tx=%s principal_usd=%s exit_usdc=%s exit_sol=%s sol_price_usdc=%s exit_value_usd=%s gas_usd=%s net_pnl_usd=%s ledger_entries=%d\n",
		shortAddress(report.PositionID),
		shortAddress(report.OpenTxHash),
		shortAddress(report.DecreaseTxHash),
		shortAddress(report.CloseTxHash),
		report.PrincipalUSD.StringFixed(6),
		report.ExitUSDC.StringFixed(6),
		report.ExitSOL.StringFixed(9),
		report.SOLPriceUSDC.StringFixed(6),
		report.ExitValueUSD.StringFixed(6),
		report.GasUSD.StringFixed(6),
		report.NetPnLUSD.StringFixed(6),
		report.LedgerEntries,
	)
	return nil
}

func resolveSolanaLPReconcilePosition(ctx context.Context, db *sql.DB, positionID string) (*domain.Position, error) {
	repo := postgres.NewPositionRepo(db)
	if strings.TrimSpace(positionID) != "" {
		pos, err := repo.FindByID(ctx, strings.TrimSpace(positionID))
		if err != nil {
			return nil, err
		}
		if pos != nil {
			return pos, nil
		}
	}
	var id string
	err := db.QueryRowContext(ctx, `
		SELECT id
		FROM positions
		WHERE chain = 2
		  AND protocol = 'pancakeswap-v3-solana'
		  AND status = 'closed'
		ORDER BY closed_at DESC NULLS LAST, opened_at DESC
		LIMIT 1
	`).Scan(&id)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("no closed pancakeswap-v3-solana position found")
	}
	if err != nil {
		return nil, fmt.Errorf("query latest closed solana lp position: %w", err)
	}
	pos, err := repo.FindByID(ctx, id)
	if err != nil {
		return nil, err
	}
	if pos == nil {
		return nil, fmt.Errorf("position disappeared after lookup: %s", id)
	}
	return pos, nil
}

func findSolanaLPExitTxHashes(ctx context.Context, db *sql.DB, positionID string) (string, string, error) {
	decreaseTx, err := latestSolanaLPEventTx(ctx, db, positionID, "decrease_broadcast")
	if err != nil {
		return "", "", err
	}
	closeTx, err := latestSolanaLPEventTx(ctx, db, positionID, "close_broadcast")
	if err != nil {
		return "", "", err
	}
	if strings.TrimSpace(decreaseTx) == "" {
		return "", "", fmt.Errorf("missing decrease_broadcast tx for position %s", positionID)
	}
	if strings.TrimSpace(closeTx) == "" {
		return "", "", fmt.Errorf("missing close_broadcast tx for position %s", positionID)
	}
	return decreaseTx, closeTx, nil
}

func resolveSolanaLPReconcileWallet(ctx context.Context, db *sql.DB, positionID string) (string, error) {
	var wallet string
	err := db.QueryRowContext(ctx, `
		SELECT wallet
		FROM canary_events
		WHERE command = 'solana_lp_close_canary'
		  AND position_id = $1
		  AND wallet <> ''
		ORDER BY created_at DESC
		LIMIT 1
	`, positionID).Scan(&wallet)
	if err != nil && err != sql.ErrNoRows {
		return "", fmt.Errorf("query solana lp reconcile wallet: %w", err)
	}
	if strings.TrimSpace(wallet) == "" {
		wallet = strings.TrimSpace(os.Getenv("SOLANA_FEE_PAYER_ADDRESS"))
	}
	if strings.TrimSpace(wallet) == "" {
		return "", fmt.Errorf("missing solana lp reconcile wallet")
	}
	return strings.TrimSpace(wallet), nil
}

func latestSolanaLPEventTx(ctx context.Context, db *sql.DB, positionID string, stage string) (string, error) {
	var txHash string
	err := db.QueryRowContext(ctx, `
		SELECT tx_hash
		FROM canary_events
		WHERE command = 'solana_lp_close_canary'
		  AND position_id = $1
		  AND stage = $2
		  AND status = 'ok'
		  AND tx_hash <> ''
		ORDER BY created_at DESC
		LIMIT 1
	`, positionID, stage).Scan(&txHash)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("query solana lp %s tx: %w", stage, err)
	}
	return txHash, nil
}

func reconcileSolanaLPRealizedPnL(ctx context.Context, cfg *config.Config, store solanaLPRealizedStore, pos *domain.Position, wallet string, decreaseTx string, closeTx string, slippageBPS int) (solanaLPRealizedPnLReport, error) {
	quotes := newSolanaFundingQuoteClient()
	solPriceUSDC, err := fetchSolanaSpotPriceUSDC(ctx, slippageBPS, quotes)
	if err != nil {
		return solanaLPRealizedPnLReport{}, err
	}
	endpoint := solanaReadinessEndpoint(cfg)
	openSummary, err := fetchSolanaTxAccounting(ctx, endpoint, pos.OpenTxHash, wallet)
	if err != nil {
		return solanaLPRealizedPnLReport{}, fmt.Errorf("open tx accounting: %w", err)
	}
	decreaseSummary, err := fetchSolanaTxAccounting(ctx, endpoint, decreaseTx, wallet)
	if err != nil {
		return solanaLPRealizedPnLReport{}, fmt.Errorf("decrease tx accounting: %w", err)
	}
	closeSummary, err := fetchSolanaTxAccounting(ctx, endpoint, closeTx, wallet)
	if err != nil {
		return solanaLPRealizedPnLReport{}, fmt.Errorf("close tx accounting: %w", err)
	}

	exitUSDC := decreaseSummary.TokenDeltaUSDC
	exitSOL := decreaseSummary.TokenDeltaSOL
	exitValueUSD := exitUSDC.Add(exitSOL.Mul(solPriceUSDC))
	gasUSD := rawSOLToDecimal(openSummary.FeeLamports + decreaseSummary.FeeLamports + closeSummary.FeeLamports).Mul(solPriceUSDC)
	netPnL := exitValueUSD.Sub(pos.AmountUSD).Sub(gasUSD)

	entries := []ports.LedgerEntry{
		{
			ID:          fmt.Sprintf("solana-lp-realized:%s:principal:%s", pos.ID, pos.OpenTxHash),
			PositionID:  pos.ID,
			Kind:        ports.LedgerEntrySwap,
			Amount:      pos.AmountUSD.Neg(),
			TokenSymbol: "USDC",
			BlockRef:    openSummary.BlockRef,
			TxHash:      pos.OpenTxHash,
		},
		{
			ID:          fmt.Sprintf("solana-lp-realized:%s:exit:%s", pos.ID, decreaseTx),
			PositionID:  pos.ID,
			Kind:        ports.LedgerEntrySwap,
			Amount:      exitValueUSD,
			TokenSymbol: "USDC",
			BlockRef:    decreaseSummary.BlockRef,
			TxHash:      decreaseTx,
		},
		{
			ID:          fmt.Sprintf("solana-lp-realized:%s:open-gas:%s", pos.ID, pos.OpenTxHash),
			PositionID:  pos.ID,
			Kind:        ports.LedgerEntryGas,
			Amount:      rawSOLToDecimal(openSummary.FeeLamports).Mul(solPriceUSDC).Neg(),
			TokenSymbol: "USDC",
			BlockRef:    openSummary.BlockRef,
			TxHash:      pos.OpenTxHash,
		},
		{
			ID:          fmt.Sprintf("solana-lp-realized:%s:decrease-gas:%s", pos.ID, decreaseTx),
			PositionID:  pos.ID,
			Kind:        ports.LedgerEntryGas,
			Amount:      rawSOLToDecimal(decreaseSummary.FeeLamports).Mul(solPriceUSDC).Neg(),
			TokenSymbol: "USDC",
			BlockRef:    decreaseSummary.BlockRef,
			TxHash:      decreaseTx,
		},
		{
			ID:          fmt.Sprintf("solana-lp-realized:%s:close-gas:%s", pos.ID, closeTx),
			PositionID:  pos.ID,
			Kind:        ports.LedgerEntryGas,
			Amount:      rawSOLToDecimal(closeSummary.FeeLamports).Mul(solPriceUSDC).Neg(),
			TokenSymbol: "USDC",
			BlockRef:    closeSummary.BlockRef,
			TxHash:      closeTx,
		},
	}
	inserted := 0
	for _, entry := range entries {
		if entry.Amount.IsZero() {
			continue
		}
		if _, err := store.Append(ctx, entry); err != nil {
			return solanaLPRealizedPnLReport{}, err
		}
		inserted++
	}
	return solanaLPRealizedPnLReport{
		PositionID:     pos.ID,
		OpenTxHash:     pos.OpenTxHash,
		DecreaseTxHash: decreaseTx,
		CloseTxHash:    closeTx,
		SOLPriceUSDC:   solPriceUSDC,
		PrincipalUSD:   pos.AmountUSD,
		ExitUSDC:       exitUSDC,
		ExitSOL:        exitSOL,
		ExitValueUSD:   exitValueUSD,
		GasUSD:         gasUSD,
		NetPnLUSD:      netPnL,
		LedgerEntries:  inserted,
	}, nil
}

type solanaTxAccounting struct {
	BlockRef       domain.BlockRef
	FeeLamports    uint64
	TokenDeltaUSDC domain.Decimal
	TokenDeltaSOL  domain.Decimal
}

func fetchSolanaTxAccounting(ctx context.Context, endpoint string, txHash string, wallet string) (solanaTxAccounting, error) {
	return fetchSolanaTxAccountingJSON(ctx, endpoint, txHash, wallet)
}

type solanaTxRPCResponse struct {
	Result *struct {
		Slot      uint64 `json:"slot"`
		BlockTime *int64 `json:"blockTime"`
		Meta      *struct {
			Err               any                     `json:"err"`
			Fee               uint64                  `json:"fee"`
			PreTokenBalances  []solanaRPCTokenBalance `json:"preTokenBalances"`
			PostTokenBalances []solanaRPCTokenBalance `json:"postTokenBalances"`
		} `json:"meta"`
	} `json:"result"`
	Error *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

type solanaRPCTokenBalance struct {
	AccountIndex  uint16 `json:"accountIndex"`
	Mint          string `json:"mint"`
	Owner         string `json:"owner"`
	UITokenAmount struct {
		Amount   string `json:"amount"`
		Decimals uint8  `json:"decimals"`
	} `json:"uiTokenAmount"`
}

func fetchSolanaTxAccountingJSON(ctx context.Context, endpoint string, txHash string, wallet string) (solanaTxAccounting, error) {
	sig, err := solanago.SignatureFromBase58(strings.TrimSpace(txHash))
	if err != nil {
		return solanaTxAccounting{}, fmt.Errorf("parse solana tx hash %s: %w", shortAddress(txHash), err)
	}
	if strings.TrimSpace(endpoint) == "" {
		endpoint = solrpc.MainNetBeta_RPC
	}
	body, err := json.Marshal(map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "getTransaction",
		"params": []any{sig.String(), map[string]any{
			"encoding":                       "jsonParsed",
			"commitment":                     "confirmed",
			"maxSupportedTransactionVersion": 0,
		}},
	})
	if err != nil {
		return solanaTxAccounting{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return solanaTxAccounting{}, err
	}
	req.Header.Set("content-type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return solanaTxAccounting{}, err
	}
	defer resp.Body.Close()
	var out solanaTxRPCResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return solanaTxAccounting{}, err
	}
	if out.Error != nil {
		return solanaTxAccounting{}, fmt.Errorf("rpc error %d: %s", out.Error.Code, out.Error.Message)
	}
	if out.Result == nil || out.Result.Meta == nil {
		return solanaTxAccounting{}, fmt.Errorf("solana tx metadata missing for %s", shortAddress(txHash))
	}
	if out.Result.Meta.Err != nil {
		return solanaTxAccounting{}, fmt.Errorf("solana tx failed: %v", out.Result.Meta.Err)
	}
	blockTime := int64(0)
	if out.Result.BlockTime != nil {
		blockTime = *out.Result.BlockTime
	}
	return solanaTxAccounting{
		BlockRef: domain.BlockRef{
			Chain:    domain.ChainSolana,
			Number:   out.Result.Slot,
			Hash:     "",
			TimeUnix: blockTime,
		},
		FeeLamports:    out.Result.Meta.Fee,
		TokenDeltaUSDC: solanaRPCTokenDeltaForMint(out.Result.Meta.PreTokenBalances, out.Result.Meta.PostTokenBalances, solanaUSDCAddress, wallet),
		TokenDeltaSOL:  solanaRPCTokenDeltaForMint(out.Result.Meta.PreTokenBalances, out.Result.Meta.PostTokenBalances, solanaWrappedSOLAddress, wallet),
	}, nil
}

func solanaRPCTokenDeltaForMint(pre []solanaRPCTokenBalance, post []solanaRPCTokenBalance, mint string, wallet string) domain.Decimal {
	preRaw := solanaRPCTokenRawByAccount(pre, mint, wallet)
	postRaw := solanaRPCTokenRawByAccount(post, mint, wallet)
	decimals := uint8(0)
	for _, item := range append(pre, post...) {
		if item.Mint == mint {
			decimals = item.UITokenAmount.Decimals
			break
		}
	}
	if decimals == 0 {
		if mint == solanaUSDCAddress {
			decimals = 6
		}
		if mint == solanaWrappedSOLAddress {
			decimals = 9
		}
	}
	total := domain.ZeroDecimal()
	accounts := make(map[uint16]struct{})
	for account := range preRaw {
		accounts[account] = struct{}{}
	}
	for account := range postRaw {
		accounts[account] = struct{}{}
	}
	for account := range accounts {
		total = total.Add(rawTokenStringToDecimal(postRaw[account], decimals).Sub(rawTokenStringToDecimal(preRaw[account], decimals)))
	}
	return total
}

func solanaRPCTokenRawByAccount(items []solanaRPCTokenBalance, mint string, wallet string) map[uint16]string {
	out := make(map[uint16]string)
	for _, item := range items {
		if item.Mint != mint {
			continue
		}
		if strings.TrimSpace(wallet) != "" && item.Owner != strings.TrimSpace(wallet) {
			continue
		}
		out[item.AccountIndex] = item.UITokenAmount.Amount
	}
	return out
}

func solanaTokenDeltaForMint(pre []solrpc.TokenBalance, post []solrpc.TokenBalance, mint string) domain.Decimal {
	preRaw := solanaTokenRawByAccount(pre, mint)
	postRaw := solanaTokenRawByAccount(post, mint)
	decimals := uint8(0)
	for _, item := range append(pre, post...) {
		if item.Mint.String() == mint && item.UiTokenAmount != nil {
			decimals = item.UiTokenAmount.Decimals
			break
		}
	}
	if decimals == 0 {
		if mint == solanaUSDCAddress {
			decimals = 6
		}
		if mint == solanaWrappedSOLAddress {
			decimals = 9
		}
	}
	total := domain.ZeroDecimal()
	accounts := make(map[uint16]struct{})
	for account := range preRaw {
		accounts[account] = struct{}{}
	}
	for account := range postRaw {
		accounts[account] = struct{}{}
	}
	for account := range accounts {
		total = total.Add(rawTokenStringToDecimal(postRaw[account], decimals).Sub(rawTokenStringToDecimal(preRaw[account], decimals)))
	}
	return total
}

func solanaTokenRawByAccount(items []solrpc.TokenBalance, mint string) map[uint16]string {
	out := make(map[uint16]string)
	for _, item := range items {
		if item.Mint.String() != mint || item.UiTokenAmount == nil {
			continue
		}
		out[item.AccountIndex] = item.UiTokenAmount.Amount
	}
	return out
}

func rawTokenStringToDecimal(raw string, decimals uint8) domain.Decimal {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return domain.ZeroDecimal()
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return domain.ZeroDecimal()
	}
	denom := domain.NewDecimalFromInt(1)
	for i := uint8(0); i < decimals; i++ {
		denom = denom.Mul(domain.NewDecimalFromInt(10))
	}
	return domain.NewDecimalFromInt(value).Div(denom)
}
