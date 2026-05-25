//go:build live

package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
	"github.com/lpbot/lpbot/internal/ports"
	"go.uber.org/zap"
)

const baseTxConfirmerInterval = 15 * time.Second

var (
	npmDecreaseLiquidityTopic = common.BytesToHash(mustKeccak4("DecreaseLiquidity(uint256,uint128,uint256,uint256)"))
	npmCollectTopic           = common.BytesToHash(mustKeccak4("Collect(uint256,address,uint256,uint256)"))
	npmCollectSelector        = string(mustKeccak4("collect((uint256,address,uint128,uint128))"))
	npmDecreaseSelector       = string(mustKeccak4("decreaseLiquidity((uint256,uint128,uint256,uint256,uint256))"))
)

type baseReceiptSource interface {
	TransactionReceipt(ctx context.Context, hash common.Hash) (*types.Receipt, error)
}

func (app *App) shouldRunBaseTxConfirmer() bool {
	return app != nil &&
		app.config != nil &&
		app.liveGate != nil &&
		app.liveGate.isExecutionMode() &&
		app.store != nil &&
		app.rpc["base"] != nil
}

func (app *App) runBaseTxConfirmerLoop(ctx context.Context) {
	ticker := time.NewTicker(baseTxConfirmerInterval)
	defer ticker.Stop()
	for {
		if err := reconcileBasePendingTxs(ctx, app.config, app.store, app.rpc["base"], app.logger, time.Now()); err != nil && ctx.Err() == nil {
			if app.logger != nil {
				app.logger.Warn("base tx confirmer reconcile failed", zap.Error(err))
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func reconcileBasePendingTxs(
	ctx context.Context,
	cfg *config.Config,
	store ports.Store,
	provider baseReceiptSource,
	logger *zap.Logger,
	now time.Time,
) error {
	if cfg == nil || store == nil || provider == nil {
		return fmt.Errorf("base tx reconcile requires config, store, and provider")
	}

	timeoutSeconds := int64(positiveOrDefault(cfg.Execution.SendTimeoutSeconds, 180))
	if err := markTimedOutBaseTxs(ctx, store, timeoutSeconds); err != nil {
		return err
	}

	pending, err := store.TxRepo().ListPendingTxs(ctx, domain.ChainBase)
	if err != nil {
		return err
	}

	var reconcileErrs []error
	for _, tx := range pending {
		if !shouldPollBaseReceipt(tx.Status) {
			continue
		}
		if err := reconcileOneBaseTx(ctx, cfg, store, provider, tx, now); err != nil {
			reconcileErrs = append(reconcileErrs, fmt.Errorf("tx %s: %w", tx.Hash, err))
			if logger != nil {
				logger.Warn("base tx reconciliation item failed",
					zap.String("tx_hash", tx.Hash),
					zap.String("status", string(tx.Status)),
					zap.Error(err))
			}
		}
	}
	if len(reconcileErrs) == 0 {
		return nil
	}
	return errors.Join(reconcileErrs...)
}

func markTimedOutBaseTxs(ctx context.Context, store ports.Store, timeoutSeconds int64) error {
	if timeoutSeconds <= 0 {
		timeoutSeconds = 180
	}
	stuckTxs, err := store.TxRepo().ListStuckTxs(ctx, domain.ChainBase, timeoutSeconds)
	if err != nil {
		return err
	}
	for _, tx := range stuckTxs {
		if tx.Status == domain.TxStuck || !tx.Status.CanTransitionTo(domain.TxStuck) {
			continue
		}
		if err := store.TxRepo().UpdateTxStatus(ctx, domain.ChainBase, tx.Hash, domain.TxStuck, nil); err != nil {
			return err
		}
		if err := markExecutionIntentByTxHash(ctx, store, domain.ChainBase, tx.Hash, domain.IntentStatusStuck, "tx exceeded stuck timeout"); err != nil {
			return err
		}
	}
	return nil
}

func shouldPollBaseReceipt(status domain.TxStatus) bool {
	switch status {
	case domain.TxSubmittedPrivate, domain.TxBroadcast, domain.TxMined, domain.TxStuck, domain.TxRFBBumped:
		return true
	default:
		return false
	}
}

func reconcileOneBaseTx(ctx context.Context, cfg *config.Config, store ports.Store, provider baseReceiptSource, tx domain.SignedTx, now time.Time) error {
	receipt, err := provider.TransactionReceipt(ctx, common.HexToHash(tx.Hash))
	if err != nil {
		if errors.Is(err, ethereum.NotFound) {
			return nil
		}
		return err
	}
	if receipt == nil {
		return nil
	}

	ref := &domain.BlockRef{
		Chain:    domain.ChainBase,
		Number:   receipt.BlockNumber.Uint64(),
		Hash:     receipt.BlockHash.Hex(),
		TimeUnix: now.Unix(),
	}

	if receipt.Status != types.ReceiptStatusSuccessful {
		return reconcileBaseRevertedTx(ctx, store, tx, ref)
	}

	if tx.Status != domain.TxMined {
		if err := store.TxRepo().UpdateTxStatus(ctx, domain.ChainBase, tx.Hash, domain.TxMined, ref); err != nil && !errors.Is(err, ports.ErrInvalidTxTransition) {
			return err
		}
	}

	if err := reconcileSuccessfulBasePosition(ctx, cfg, store, tx, receipt); err != nil {
		return err
	}

	latest, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, tx.Hash)
	if err != nil {
		return err
	}
	if latest.Status == domain.TxConfirmed {
		return markExecutionIntentByTxHash(ctx, store, domain.ChainBase, tx.Hash, domain.IntentStatusReconciled, "already confirmed and reconciled")
	}
	if err := store.TxRepo().UpdateTxStatus(ctx, domain.ChainBase, tx.Hash, domain.TxConfirmed, ref); err != nil {
		return err
	}
	return markExecutionIntentByTxHash(ctx, store, domain.ChainBase, tx.Hash, domain.IntentStatusReconciled, "receipt confirmed and reconciled")
}

func reconcileBaseRevertedTx(ctx context.Context, store ports.Store, tx domain.SignedTx, ref *domain.BlockRef) error {
	latest, err := store.TxRepo().GetTxByHash(ctx, domain.ChainBase, tx.Hash)
	if err != nil {
		return err
	}
	if latest.Status != domain.TxReverted {
		if err := store.TxRepo().UpdateTxStatus(ctx, domain.ChainBase, tx.Hash, domain.TxReverted, ref); err != nil && !errors.Is(err, ports.ErrInvalidTxTransition) {
			return err
		}
	}
	if err := markExecutionIntentByTxHash(ctx, store, domain.ChainBase, tx.Hash, domain.IntentStatusFailed, "receipt reverted"); err != nil {
		return err
	}

	position, err := findOpeningPositionByOpenTxHash(ctx, store.PositionRepo(), tx.Hash)
	if err != nil {
		return err
	}
	if position != nil {
		return updatePositionStatus(ctx, store.PositionRepo(), position, domain.StatusRejected)
	}

	action, tokenID := classifyNPMTx(tx)
	if tokenID == "" {
		return nil
	}
	position, err = findPositionByTokenID(ctx, store.PositionRepo(), tokenID, domain.StatusExiting, domain.StatusOpen, domain.StatusOpening)
	if err != nil {
		return err
	}
	if position == nil {
		return nil
	}
	if action == "collect" && position.Status == domain.StatusOpen {
		return nil
	}
	if position.Status == domain.StatusExiting {
		return updatePositionStatus(ctx, store.PositionRepo(), position, domain.StatusExitFailed)
	}
	return nil
}

func reconcileSuccessfulBasePosition(ctx context.Context, cfg *config.Config, store ports.Store, tx domain.SignedTx, receipt *types.Receipt) error {
	npmAddress := strings.TrimSpace(cfg.Execution.NPMBaseAddress)
	if npmAddress == "" {
		npmAddress = defaultBaseUniswapV3NPMAddress
	}
	npm := common.HexToAddress(npmAddress)

	tokenID, liquidity, amount0, amount1, mintErr := parseMintReceiptDetails(receipt, npm)
	if mintErr == nil {
		position, err := findOpeningPositionByMintTx(ctx, store, cfg, tx.Hash)
		if err != nil {
			return err
		}
		if position == nil {
			return fmt.Errorf("no opening position found for mint tx %s", tx.Hash)
		}
		return persistSuccessfulMintReconcile(ctx, store.PositionRepo(), position, tx.Hash, tokenID, liquidity, amount0, amount1, receipt)
	}

	action, parsedTokenID := classifyNPMTx(tx)
	if parsedTokenID == "" {
		return nil
	}
	position, err := findPositionByTokenID(ctx, store.PositionRepo(), parsedTokenID, domain.StatusExiting, domain.StatusOpen, domain.StatusOpening)
	if err != nil {
		return err
	}
	if position == nil {
		return nil
	}

	switch action {
	case "decrease":
		return persistPositionMetadata(ctx, store.PositionRepo(), position, map[string]string{
			"last_decrease_tx_hash": tx.Hash,
			"last_receipt_block":    receipt.BlockHash.Hex(),
		})
	case "collect":
		if err := persistPositionMetadata(ctx, store.PositionRepo(), position, map[string]string{
			"last_collect_tx_hash": tx.Hash,
			"last_receipt_block":   receipt.BlockHash.Hex(),
		}); err != nil {
			return err
		}
		if position.Status == domain.StatusExiting {
			return updatePositionStatus(ctx, store.PositionRepo(), position, domain.StatusClosed)
		}
	}
	return nil
}

func parseMintReceiptDetails(receipt *types.Receipt, npm common.Address) (tokenID, liquidity, amount0, amount1 string, err error) {
	if receipt == nil {
		return "", "", "", "", fmt.Errorf("receipt is nil")
	}
	for _, log := range receipt.Logs {
		if log == nil || log.Address != npm || len(log.Topics) != 4 || log.Topics[0] != erc721TransferTopic || log.Topics[1] != zeroTopic {
			continue
		}
		tokenID = new(big.Int).SetBytes(log.Topics[3].Bytes()).String()
		break
	}
	if tokenID == "" {
		return "", "", "", "", fmt.Errorf("mint receipt does not contain npm ERC721 mint transfer")
	}

	tokenIDTopic := bigIntToTopic(mustTokenIDBig(tokenID))
	for _, log := range receipt.Logs {
		if log == nil || log.Address != npm || len(log.Topics) < 2 || log.Topics[0] != npmIncreaseLiquidityTopic || log.Topics[1] != tokenIDTopic {
			continue
		}
		if len(log.Data) < 96 {
			return "", "", "", "", fmt.Errorf("npm IncreaseLiquidity data too short: %d", len(log.Data))
		}
		liquidity = new(big.Int).SetBytes(log.Data[0:32]).String()
		amount0 = new(big.Int).SetBytes(log.Data[32:64]).String()
		amount1 = new(big.Int).SetBytes(log.Data[64:96]).String()
		return tokenID, liquidity, amount0, amount1, nil
	}
	return "", "", "", "", fmt.Errorf("mint receipt does not contain matching npm IncreaseLiquidity event for token_id %s", tokenID)
}

func classifyNPMTx(tx domain.SignedTx) (action string, tokenID string) {
	if len(tx.Data) < 36 {
		return "", ""
	}
	selector := string(tx.Data[:4])
	switch selector {
	case npmCollectSelector:
		return "collect", new(big.Int).SetBytes(tx.Data[4:36]).String()
	case npmDecreaseSelector:
		return "decrease", new(big.Int).SetBytes(tx.Data[4:36]).String()
	default:
		return "", ""
	}
}

func findOpeningPositionByMintTx(ctx context.Context, store ports.Store, cfg *config.Config, txHash string) (*domain.Position, error) {
	position, err := findOpeningPositionByOpenTxHash(ctx, store.PositionRepo(), txHash)
	if err != nil || position != nil {
		return position, err
	}
	return findOpeningPositionByCanaryEvent(ctx, store, cfg, txHash)
}

func findOpeningPositionByOpenTxHash(ctx context.Context, repo ports.PositionRepo, txHash string) (*domain.Position, error) {
	for _, status := range []domain.PositionStatus{domain.StatusOpening, domain.StatusApproved, domain.StatusIntended} {
		positions, err := repo.FindByChainAndStatus(ctx, domain.ChainBase, status)
		if err != nil {
			return nil, err
		}
		for _, position := range positions {
			if strings.EqualFold(strings.TrimSpace(position.OpenTxHash), strings.TrimSpace(txHash)) {
				return position, nil
			}
		}
	}
	return nil, nil
}

func findOpeningPositionByCanaryEvent(ctx context.Context, store ports.Store, cfg *config.Config, txHash string) (*domain.Position, error) {
	if cfg == nil {
		return nil, nil
	}
	backend := strings.ToLower(strings.TrimSpace(cfg.Store.Backend))
	if backend != "postgres" && backend != "postgresql" && backend != "pg" {
		return nil, nil
	}
	dbStore, ok := any(store).(interface{ DB() *sql.DB })
	if !ok || dbStore.DB() == nil {
		return nil, nil
	}
	var positionID string
	err := dbStore.DB().QueryRowContext(ctx, `
		SELECT position_id
		FROM canary_events
		WHERE tx_hash = $1
		  AND position_id <> ''
		ORDER BY created_at DESC
		LIMIT 1
	`, txHash).Scan(&positionID)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return store.PositionRepo().FindByID(ctx, positionID)
}

func findPositionByTokenID(ctx context.Context, repo ports.PositionRepo, tokenID string, statuses ...domain.PositionStatus) (*domain.Position, error) {
	for _, status := range statuses {
		positions, err := repo.FindByChainAndStatus(ctx, domain.ChainBase, status)
		if err != nil {
			return nil, err
		}
		for _, position := range positions {
			if strings.TrimSpace(position.TokenID) == strings.TrimSpace(tokenID) {
				return position, nil
			}
		}
	}
	return nil, nil
}

func persistSuccessfulMintReconcile(
	ctx context.Context,
	repo ports.PositionRepo,
	position *domain.Position,
	txHash string,
	tokenID string,
	liquidity string,
	amount0 string,
	amount1 string,
	receipt *types.Receipt,
) error {
	if position == nil {
		return fmt.Errorf("position is nil")
	}
	position.TokenID = tokenID
	position.OpenTxHash = txHash
	position.Status = domain.StatusOpen
	updates := map[string]string{
		"open_tx_hash":   txHash,
		"token_id":       tokenID,
		"liquidity":      liquidity,
		"actual_amount0": amount0,
		"actual_amount1": amount1,
		"receipt_block":  fmt.Sprintf("%d", receipt.BlockNumber.Uint64()),
		"receipt_hash":   receipt.BlockHash.Hex(),
		"reconciled_at":  fmt.Sprintf("%d", time.Now().Unix()),
	}
	merged, err := mergePositionMetadata(position.MetadataJSON, updates)
	if err != nil {
		return err
	}
	position.MetadataJSON = merged
	return repo.Save(ctx, position)
}

func persistPositionMetadata(ctx context.Context, repo ports.PositionRepo, position *domain.Position, updates map[string]string) error {
	if position == nil {
		return nil
	}
	merged, err := mergePositionMetadata(position.MetadataJSON, updates)
	if err != nil {
		return err
	}
	position.MetadataJSON = merged
	return repo.Save(ctx, position)
}

func mergePositionMetadata(raw string, updates map[string]string) (string, error) {
	payload := map[string]any{}
	trimmed := strings.TrimSpace(raw)
	if trimmed != "" && trimmed != "{}" {
		if err := json.Unmarshal([]byte(trimmed), &payload); err != nil {
			return "", fmt.Errorf("decode position metadata: %w", err)
		}
	}
	for key, value := range updates {
		payload[key] = value
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("encode position metadata: %w", err)
	}
	return string(encoded), nil
}

func updatePositionStatus(ctx context.Context, repo ports.PositionRepo, position *domain.Position, status domain.PositionStatus) error {
	if position == nil || position.Status == status {
		return nil
	}
	position.Status = status
	return repo.Save(ctx, position)
}

func attachOpenTxHashToPosition(ctx context.Context, repo ports.PositionRepo, positionID string, txHash string) error {
	position, err := repo.FindByID(ctx, positionID)
	if err != nil {
		return err
	}
	if position == nil {
		return fmt.Errorf("position not found: %s", positionID)
	}
	position.OpenTxHash = txHash
	merged, err := mergePositionMetadata(position.MetadataJSON, map[string]string{
		"pending_open_tx_hash": txHash,
	})
	if err != nil {
		return err
	}
	position.MetadataJSON = merged
	return repo.Save(ctx, position)
}
