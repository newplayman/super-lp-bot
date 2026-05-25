package ports

import (
	"context"

	"github.com/lpbot/lpbot/internal/domain"
)

type ExecutionIntentRepo interface {
	Reserve(ctx context.Context, intent *domain.ExecutionIntent) error
	FindByID(ctx context.Context, id string) (*domain.ExecutionIntent, error)
	FindByIdempotencyKey(ctx context.Context, key string) (*domain.ExecutionIntent, error)
	FindByTxHash(ctx context.Context, chain domain.ChainID, txHash string) (*domain.ExecutionIntent, error)
	Update(ctx context.Context, intent *domain.ExecutionIntent) error
}

var ErrExecutionIntentNotFound = &ExecutionIntentNotFoundError{}

type ExecutionIntentNotFoundError struct{}

func (e *ExecutionIntentNotFoundError) Error() string { return "execution intent not found" }
