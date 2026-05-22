//go:build live

package main

import (
	"context"
	"database/sql"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

var (
	erc721TransferTopic       = crypto.Keccak256Hash([]byte("Transfer(address,address,uint256)"))
	npmIncreaseLiquidityTopic = crypto.Keccak256Hash([]byte("IncreaseLiquidity(uint256,uint128,uint256,uint256)"))
	zeroTopic                 common.Hash
)

type canaryMintReconcileReport struct {
	PositionID    string
	PoolID        string
	Wallet        string
	TokenID       string
	TxHash        string
	Amount0Raw    *big.Int
	Amount1Raw    *big.Int
	ActualUSD     domain.Decimal
	ActualUSDCRaw *big.Int
	ActualWETHRaw *big.Int
}

func runCanaryMintReconcile(ctx context.Context, cfg *config.Config, txHash string) (err error) {
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}
	txHash = strings.TrimSpace(txHash)
	if !common.IsHexAddress(strings.TrimPrefix(txHash, "0x")) && !strings.HasPrefix(txHash, "0x") {
		return fmt.Errorf("--tx-hash must be a 0x transaction hash")
	}
	if !common.IsHexAddress("0x" + strings.TrimPrefix(strings.TrimSpace(cfg.Execution.NPMBaseAddress), "0x")) {
		return fmt.Errorf("npm base address is invalid")
	}

	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()

	report := canaryMintReconcileReport{TxHash: txHash}
	defer func() {
		if err != nil {
			_ = state.Record(ctx, canaryEvent{
				Command:    "canary_reconcile_mint",
				Stage:      "failed",
				Status:     "failed",
				PositionID: report.PositionID,
				PoolID:     report.PoolID,
				Wallet:     report.Wallet,
				TokenID:    report.TokenID,
				TxHash:     txHash,
				ErrorMsg:   err.Error(),
			})
		}
	}()

	positionID, poolID, wallet, err := lookupCanaryMintEvent(ctx, state.db, txHash)
	if err != nil {
		return err
	}
	report.PositionID = positionID
	report.PoolID = poolID
	report.Wallet = wallet

	provider, err := newCanaryMintProvider(ctx, cfg)
	if err != nil {
		return err
	}
	pool, err := loadCanaryPreflightPool(ctx, provider, poolID)
	if err != nil {
		return err
	}
	receipt, err := provider.TransactionReceipt(ctx, common.HexToHash(txHash))
	if err != nil {
		return fmt.Errorf("read mint receipt: %w", err)
	}
	if receipt.Status != types.ReceiptStatusSuccessful {
		return fmt.Errorf("mint receipt status is not successful: %d", receipt.Status)
	}

	npm := common.HexToAddress(strings.TrimSpace(cfg.Execution.NPMBaseAddress))
	tokenID, amount0, amount1, err := parseCanaryMintReceipt(receipt, npm, wallet)
	if err != nil {
		return err
	}
	report.TokenID = tokenID
	report.Amount0Raw = amount0
	report.Amount1Raw = amount1

	decimals0, err := tokenDecimals(ctx, provider, pool.Token0)
	if err != nil {
		return fmt.Errorf("token0 decimals: %w", err)
	}
	decimals1, err := tokenDecimals(ctx, provider, pool.Token1)
	if err != nil {
		return fmt.Errorf("token1 decimals: %w", err)
	}
	price0, price1, err := inferBaseTokenPricesUSD(pool, decimals0, decimals1)
	if err != nil {
		return err
	}
	actualUSD := decimalFromRawAmount(amount0, decimals0).Mul(price0).Add(decimalFromRawAmount(amount1, decimals1).Mul(price1))
	report.ActualUSD = actualUSD
	report.ActualUSDCRaw = rawForToken(pool, baseUSDCAddress, amount0, amount1)
	report.ActualWETHRaw = rawForToken(pool, baseWETHAddress, amount0, amount1)

	if err := persistCanaryMintReconcile(ctx, state.db, report); err != nil {
		return err
	}
	if err := state.Record(ctx, canaryEvent{
		Command:         "canary_reconcile_mint",
		Stage:           "receipt_reconciled",
		Status:          "ok",
		PositionID:      report.PositionID,
		PoolID:          report.PoolID,
		Wallet:          report.Wallet,
		TokenID:         report.TokenID,
		TxHash:          report.TxHash,
		AmountUSD:       report.ActualUSD.String(),
		RequiredUSDCRaw: report.ActualUSDCRaw.String(),
		RequiredWETHRaw: report.ActualWETHRaw.String(),
		Message:         "mint receipt confirmed; token_id and actual principal reconciled",
	}); err != nil {
		return err
	}

	fmt.Printf("canary_mint_reconciled tx=%s position=%s token_id=%s actual_usd=%s actual_usdc_raw=%s actual_weth_raw=%s\n",
		report.TxHash, report.PositionID, report.TokenID, report.ActualUSD.String(), report.ActualUSDCRaw.String(), report.ActualWETHRaw.String())
	return nil
}

func lookupCanaryMintEvent(ctx context.Context, db *sql.DB, txHash string) (string, string, string, error) {
	var positionID, poolID, wallet string
	err := db.QueryRowContext(ctx, `
		SELECT position_id, pool_id, wallet
		FROM canary_events
		WHERE tx_hash = $1
		  AND command = 'canary_mint'
		  AND position_id <> ''
		  AND pool_id <> ''
		ORDER BY created_at DESC
		LIMIT 1
	`, txHash).Scan(&positionID, &poolID, &wallet)
	if err == sql.ErrNoRows {
		return "", "", "", fmt.Errorf("no canary mint event found for tx_hash %s", txHash)
	}
	if err != nil {
		return "", "", "", fmt.Errorf("lookup canary mint event: %w", err)
	}
	return positionID, poolID, wallet, nil
}

func parseCanaryMintReceipt(receipt *types.Receipt, npm common.Address, wallet string) (string, *big.Int, *big.Int, error) {
	tokenID := ""
	for _, log := range receipt.Logs {
		if log == nil || log.Address != npm || len(log.Topics) != 4 || log.Topics[0] != erc721TransferTopic || log.Topics[1] != zeroTopic {
			continue
		}
		if wallet != "" && log.Topics[2] != addressToTopic(common.HexToAddress(wallet)) {
			continue
		}
		tokenID = new(big.Int).SetBytes(log.Topics[3].Bytes()).String()
		break
	}
	if tokenID == "" {
		return "", nil, nil, fmt.Errorf("mint receipt does not contain npm ERC721 mint transfer")
	}

	tokenIDTopic := bigIntToTopic(mustTokenIDBig(tokenID))
	for _, log := range receipt.Logs {
		if log == nil || log.Address != npm || len(log.Topics) < 2 || log.Topics[0] != npmIncreaseLiquidityTopic || log.Topics[1] != tokenIDTopic {
			continue
		}
		if len(log.Data) < 96 {
			return "", nil, nil, fmt.Errorf("npm IncreaseLiquidity data too short: %d", len(log.Data))
		}
		amount0 := new(big.Int).SetBytes(log.Data[32:64])
		amount1 := new(big.Int).SetBytes(log.Data[64:96])
		return tokenID, amount0, amount1, nil
	}
	return "", nil, nil, fmt.Errorf("mint receipt does not contain matching npm IncreaseLiquidity event for token_id %s", tokenID)
}

func persistCanaryMintReconcile(ctx context.Context, db *sql.DB, report canaryMintReconcileReport) error {
	now := time.Now().Unix()
	result, err := db.ExecContext(ctx, `
		UPDATE positions
		SET token_id = $1,
		    amount_usd = CASE
		        WHEN status = 'closed' AND amount_usd <> '' THEN amount_usd
		        ELSE $2
		    END,
		    status = CASE
		        WHEN status IN ('intended', 'opening') THEN 'open'
		        ELSE status
		    END,
		    closed_at = CASE
		        WHEN status IN ('intended', 'opening', 'open') THEN NULL
		        ELSE closed_at
		    END
		WHERE id = $3
	`, report.TokenID, report.ActualUSD.String(), report.PositionID)
	if err != nil {
		return fmt.Errorf("update reconciled canary position: %w", err)
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("read reconciled position rows affected: %w", err)
	}
	if affected != 1 {
		return fmt.Errorf("expected to reconcile 1 position %s, updated %d", report.PositionID, affected)
	}
	_, err = db.ExecContext(ctx, `
		UPDATE transactions
		SET status = 'confirmed'
		WHERE tx_hash = $1
		  AND status IN ('built', 'broadcast')
	`, report.TxHash)
	if err != nil {
		return fmt.Errorf("mark reconciled mint tx confirmed: %w", err)
	}
	_, err = db.ExecContext(ctx, `
		DELETE FROM shadow_exit_actions
		WHERE position_id = $1
		  AND tx_hash LIKE 'shadow-exit-tx-%'
	`, report.PositionID)
	if err != nil {
		return fmt.Errorf("delete stale fake shadow close actions: %w", err)
	}
	_, err = db.ExecContext(ctx, `
		DELETE FROM shadow_position_marks
		WHERE position_id = $1
		  AND status = 'closed'
		  AND mark_time >= $2
	`, report.PositionID, now-86400)
	if err != nil {
		return fmt.Errorf("delete stale fake closed marks: %w", err)
	}
	return nil
}

func rawForToken(pool domain.Pool, token string, amount0 *big.Int, amount1 *big.Int) *big.Int {
	if strings.EqualFold(pool.Token0.String(), token) {
		return new(big.Int).Set(amount0)
	}
	if strings.EqualFold(pool.Token1.String(), token) {
		return new(big.Int).Set(amount1)
	}
	return new(big.Int)
}

func addressToTopic(address common.Address) common.Hash {
	return common.BytesToHash(address.Bytes())
}

func bigIntToTopic(value *big.Int) common.Hash {
	if value == nil {
		return common.Hash{}
	}
	return common.BytesToHash(value.Bytes())
}
