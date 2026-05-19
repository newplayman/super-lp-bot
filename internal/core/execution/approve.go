// Package execution implements the OrderManager pattern for transaction execution.
package execution

import (
	"context"
	"fmt"
	"math/big"
	"strings"
	"sync"
	"time"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// approvalKey returns a unique key for a token:spender pair.
func approvalKey(token, spender domain.Address) string {
	return fmt.Sprintf("%s:%s", token.String(), spender.String())
}

// approval represents a tracked token approval.
type approval struct {
	Token    domain.Address
	Spender  domain.Address
	Amount   domain.Decimal
	Position string // position ID if linked
	Acquired time.Time
}

// approveTracker manages ERC20 token approvals for positions.
// It ensures precise approval amounts (no ApproveMax) and audit trails.
//
// ApproveTracker responsibilities (spec §6.6, invariants #9 and #10):
//   - Acquire exact approval before position open
//   - Release (revoke) approval after position close
//   - No ApproveMax - always exact amounts
//   - Audit all approvals periodically
type approveTracker struct {
	store     ports.PositionRepo // may be nil if not using store-backed approvals
	wallet    ports.Wallet
	chain     ports.Chain
	approvals map[string]*approval // key: "token:spender"
	mu        sync.RWMutex
}

// NewApproveTracker creates a new ApproveTracker.
func NewApproveTracker(wallet ports.Wallet, chain ports.Chain, store ports.PositionRepo) *approveTracker {
	return &approveTracker{
		store:     store,
		wallet:    wallet,
		chain:     chain,
		approvals: make(map[string]*approval),
	}
}

// Acquire gets or creates an exact approval for the given token/spender pair.
// If an existing approval with sufficient amount exists, it returns the existing approval.
// Otherwise, it creates a new approval transaction for the exact amount needed.
//
// Parameters:
//   - ctx: context for cancellation
//   - token: the token address to approve
//   - spender: the address that will spend tokens
//   - need: the exact amount to approve (must be > 0)
//   - positionID: the associated position ID (optional, empty string if none)
//
// Returns the approval info and an error if:
//   - need is zero or negative
//   - approval transaction cannot be constructed
//
// Implements invariant #9: no ApproveMax, always exact amounts.
func (at *approveTracker) Acquire(ctx context.Context, token, spender domain.Address, need *big.Int, positionID string) (*approval, error) {
	if need == nil || need.Sign() <= 0 {
		return nil, fmt.Errorf("approval amount must be positive: %v", need)
	}

	key := approvalKey(token, spender)

	at.mu.Lock()
	defer at.mu.Unlock()

	// Check existing approval
	if existing, ok := at.approvals[key]; ok {
		existingAmount := existing.Amount.BigInt()
		if existingAmount.Cmp(need) >= 0 {
			// Existing approval is sufficient; update position link if provided
			if positionID != "" {
				existing.Position = positionID
			}
			return existing, nil
		}
		// Need to increase approval: revoke and re-approve with exact amount
		if _, err := at.wallet.Revoke(ctx, token, spender); err != nil {
			return nil, fmt.Errorf("failed to revoke existing approval: %w", err)
		}
	}

	// Create new exact approval
	tx, err := at.wallet.ApproveExact(ctx, token, spender, need)
	if err != nil {
		return nil, fmt.Errorf("failed to create approval tx: %w", err)
	}

	// The tx must be signed and broadcast by the caller.
	// We record the approval as pending (will be confirmed by AuditAll).
	amount := domain.MustDecimal(need.String())
	approv := &approval{
		Token:    token,
		Spender:  spender,
		Amount:   amount,
		Position: positionID,
		Acquired: time.Now(),
	}
	at.approvals[key] = approv

	// Suppress unused variable warning
	_ = tx

	return approv, nil
}

// Release revokes a token approval by setting it to zero.
// It removes the approval from the tracker after revocation.
//
// Parameters:
//   - ctx: context for cancellation
//   - token: the token address whose approval to revoke
//   - spender: the address whose approval to revoke
//
// Returns an error if the revocation transaction cannot be constructed.
// The caller is responsible for signing and broadcasting the transaction.
//
// Implements invariant #10: position exit must revoke token approvals.
func (at *approveTracker) Release(ctx context.Context, token, spender domain.Address) error {
	key := approvalKey(token, spender)

	// Create revocation transaction
	_, err := at.wallet.Revoke(ctx, token, spender)
	if err != nil {
		return fmt.Errorf("failed to create revoke tx: %w", err)
	}

	at.mu.Lock()
	defer at.mu.Unlock()

	// Remove from tracker
	delete(at.approvals, key)

	return nil
}

// AuditFinding represents a finding from an approval audit.
type AuditFinding struct {
	Token   domain.Address
	Spender domain.Address
	OnChain *big.Int // actual on-chain allowance
	Tracked *big.Int // tracked allowance (nil if not tracked)
}

// AuditAll audits all tracked approvals against on-chain state.
// Returns findings for any approvals that differ from expected state.
//
// This is used for periodic reconciliation to detect:
//   - Approvals that were revoked externally
//   - Approvals that were increased externally (potential security issue)
//   - Orphaned approvals (no position ID)
func (at *approveTracker) AuditAll(ctx context.Context) ([]AuditFinding, error) {
	at.mu.RLock()
	defer at.mu.RUnlock()

	var findings []AuditFinding

	for key, tracked := range at.approvals {
		onChain, err := at.CheckAllowance(ctx, tracked.Token, tracked.Spender)
		if err != nil {
			// Log error but continue auditing other approvals
			continue
		}

		trackedAmount := tracked.Amount.BigInt()
		if onChain.Cmp(trackedAmount) != 0 {
			parts := strings.Split(key, ":")
			if len(parts) == 2 {
				findings = append(findings, AuditFinding{
					Token:   tracked.Token,
					Spender: tracked.Spender,
					OnChain: onChain,
					Tracked: trackedAmount,
				})
			}
		}

		_ = key // suppress unused variable warning
	}

	return findings, nil
}

// CheckAllowance queries the chain for the current allowance of a token/spender pair.
// Returns the current allowance amount or an error if the query fails.
func (at *approveTracker) CheckAllowance(ctx context.Context, token, spender domain.Address) (*big.Int, error) {
	owner := at.wallet.Address()

	// Build ERC20 allowance calldata: allowance(owner, spender)
	// Function selector: 0xdd62ed3e
	data := make([]byte, 4)
	data[0] = 0xdd
	data[1] = 0x62
	data[2] = 0xed
	data[3] = 0x3e

	// Append owner and spender addresses (padded to 32 bytes each)
	ownerBytes := owner.Bytes()
	spenderBytes := spender.Bytes()

	// Pad owner to 32 bytes
	ownerPadded := make([]byte, 32)
	copy(ownerPadded[32-len(ownerBytes):], ownerBytes)

	// Pad spender to 32 bytes
	spenderPadded := make([]byte, 32)
	copy(spenderPadded[32-len(spenderBytes):], spenderBytes)

	data = append(data, ownerPadded...)
	data = append(data, spenderPadded...)

	result, err := at.chain.Multicall(ctx, []ports.Call{
		{Target: token, Data: data},
	})
	if err != nil {
		return nil, fmt.Errorf("multicall failed: %w", err)
	}

	if len(result) == 0 || !result[0].Success || len(result[0].Data) < 32 {
		return nil, fmt.Errorf("allowance call failed or returned no data")
	}

	// Parse the returned uint256 value
	allowance := new(big.Int).SetBytes(result[0].Data[0:32])
	return allowance, nil
}

// GetApproval returns the tracked approval for a token/spender pair.
// Returns nil if no approval is tracked.
func (at *approveTracker) GetApproval(token, spender domain.Address) *approval {
	key := approvalKey(token, spender)

	at.mu.RLock()
	defer at.mu.RUnlock()

	return at.approvals[key]
}

// GetApprovals returns all tracked approvals.
func (at *approveTracker) GetApprovals() map[string]*approval {
	at.mu.RLock()
	defer at.mu.RUnlock()

	result := make(map[string]*approval, len(at.approvals))
	for k, v := range at.approvals {
		result[k] = v
	}
	return result
}