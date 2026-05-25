package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

func newExecutionIntent(mode string, chain domain.ChainID, poolID string, positionID string, action string, reason string, strategyTime time.Time) *domain.ExecutionIntent {
	epoch := strategyEpoch(strategyTime)
	key := buildExecutionIntentKey(mode, chain, poolID, positionID, action, epoch)
	return &domain.ExecutionIntent{
		ID:                 "intent-" + shortHash(key),
		Mode:               mode,
		Chain:              chain,
		PoolID:             poolID,
		PositionID:         positionID,
		Action:             action,
		Status:             domain.IntentStatusIntended,
		IdempotencyKey:     key,
		Reason:             reason,
		RiskSnapshotJSON:   "{}",
		SizingSnapshotJSON: "{}",
		CreatedAt:          strategyTime.UnixMilli(),
		UpdatedAt:          strategyTime.UnixMilli(),
	}
}

func buildExecutionIntentKey(mode string, chain domain.ChainID, poolID string, positionID string, action string, epoch string) string {
	return strings.Join([]string{
		strings.TrimSpace(mode),
		string(chain),
		strings.TrimSpace(poolID),
		strings.TrimSpace(positionID),
		strings.TrimSpace(action),
		strings.TrimSpace(epoch),
	}, ":")
}

func strategyEpoch(ts time.Time) string {
	if ts.IsZero() {
		ts = time.Now().UTC()
	}
	return ts.UTC().Format("200601021504")
}

func shortHash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])[:24]
}

func reserveExecutionIntent(ctx context.Context, repo ports.ExecutionIntentRepo, intent *domain.ExecutionIntent) error {
	if repo == nil {
		return nil
	}
	if err := repo.Reserve(ctx, intent); err != nil {
		return err
	}
	return nil
}

func updateExecutionIntent(ctx context.Context, repo ports.ExecutionIntentRepo, intent *domain.ExecutionIntent, status domain.ExecutionIntentStatus, unsignedTxHash string, signedTxHash string, txHash string, reason string) error {
	if repo == nil || intent == nil {
		return nil
	}
	intent.Status = status
	if unsignedTxHash != "" {
		intent.UnsignedTxHash = unsignedTxHash
	}
	if signedTxHash != "" {
		intent.SignedTxHash = signedTxHash
	}
	if txHash != "" {
		intent.TxHash = txHash
	}
	if reason != "" {
		intent.Reason = reason
	}
	return repo.Update(ctx, intent)
}

func intentStatusFromTxStatus(status domain.TxStatus) domain.ExecutionIntentStatus {
	switch status {
	case domain.TxSubmittedPrivate:
		return domain.IntentStatusSubmittedPrivate
	case domain.TxBroadcast:
		return domain.IntentStatusBroadcast
	case domain.TxMined:
		return domain.IntentStatusMined
	case domain.TxConfirmed:
		return domain.IntentStatusConfirmed
	case domain.TxStuck:
		return domain.IntentStatusStuck
	case domain.TxFailed, domain.TxReverted, domain.TxReorged:
		return domain.IntentStatusFailed
	default:
		return domain.IntentStatusSigned
	}
}

func markExecutionIntentByTxHash(ctx context.Context, store ports.Store, chain domain.ChainID, txHash string, status domain.ExecutionIntentStatus, reason string) error {
	if store == nil || store.ExecutionIntentRepo() == nil || strings.TrimSpace(txHash) == "" {
		return nil
	}
	intent, err := store.ExecutionIntentRepo().FindByTxHash(ctx, chain, txHash)
	if errors.Is(err, ports.ErrExecutionIntentNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	return updateExecutionIntent(ctx, store.ExecutionIntentRepo(), intent, status, "", "", txHash, reason)
}

func buildSizingSnapshotJSON(amountUSD domain.Decimal, extra map[string]string) string {
	payload := map[string]string{"amount_usd": amountUSD.String()}
	for key, value := range extra {
		payload[key] = value
	}
	raw, err := marshalStringMap(payload)
	if err != nil {
		return "{}"
	}
	return raw
}

func marshalStringMap(payload map[string]string) (string, error) {
	if len(payload) == 0 {
		return "{}", nil
	}
	buf, err := jsonMarshal(payload)
	if err != nil {
		return "", err
	}
	return string(buf), nil
}

func jsonMarshal(value any) ([]byte, error) {
	return json.Marshal(value)
}
