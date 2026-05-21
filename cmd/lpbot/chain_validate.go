package main

import (
	"context"
	"fmt"
	"math/big"
	"strings"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"

	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
)

type chainValidationResult struct {
	OK     bool
	Stage  string
	Reason string
}

func (app *App) validatePoolOnChain(ctx context.Context, pool domain.Pool) chainValidationResult {
	provider := app.rpcProviderForChain(pool.Chain)
	if provider == nil {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_rpc_unavailable",
			Reason: fmt.Sprintf("no rpc provider configured for chain %s", pool.Chain),
		}
	}

	poolAddr, err := domain.ParseAddress(pool.ID)
	if err != nil {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_pool_invalid",
			Reason: fmt.Sprintf("pool address invalid: %v", err),
		}
	}

	code, err := provider.CodeAt(ctx, poolAddr, nil)
	if err != nil {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_code_error",
			Reason: err.Error(),
		}
	}
	if len(code) == 0 {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_code_missing",
			Reason: "pool contract has no bytecode on chain",
		}
	}

	token0, err := callAddressMethod(ctx, provider, poolAddr, "token0()")
	if err != nil {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_token0_error",
			Reason: err.Error(),
		}
	}
	token1, err := callAddressMethod(ctx, provider, poolAddr, "token1()")
	if err != nil {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_token1_error",
			Reason: err.Error(),
		}
	}
	if !strings.EqualFold(token0.String(), pool.Token0.String()) {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_token0_mismatch",
			Reason: fmt.Sprintf("token0 mismatch: chain=%s metadata=%s", token0, pool.Token0),
		}
	}
	if !strings.EqualFold(token1.String(), pool.Token1.String()) {
		return chainValidationResult{
			OK:     false,
			Stage:  "chain_token1_mismatch",
			Reason: fmt.Sprintf("token1 mismatch: chain=%s metadata=%s", token1, pool.Token1),
		}
	}

	v3Fee, feeErr := callUintMethod(ctx, provider, poolAddr, "fee()")
	slot0Data, slot0Err := callRawMethod(ctx, provider, poolAddr, "slot0()")
	liquidityData, liquidityErr := callRawMethod(ctx, provider, poolAddr, "liquidity()")
	if slot0Err == nil && len(slot0Data) >= 32 && liquidityErr == nil && len(liquidityData) >= 32 {
		if pool.FeeBPS > 0 && v3Fee > 0 {
			onChainFeeBPS := normalizeV3FeeToBPS(v3Fee)
			if onChainFeeBPS > 0 && onChainFeeBPS != pool.FeeBPS {
				return chainValidationResult{
					OK:     false,
					Stage:  "chain_fee_mismatch",
					Reason: fmt.Sprintf("fee mismatch: chain=%dbps metadata=%dbps", onChainFeeBPS, pool.FeeBPS),
				}
			}
		}
		return chainValidationResult{
			OK:     true,
			Stage:  "chain_v3_validated",
			Reason: "verified code, tokens, slot0, liquidity",
		}
	}

	reservesData, reservesErr := callRawMethod(ctx, provider, poolAddr, "getReserves()")
	if reservesErr == nil && len(reservesData) >= 96 {
		return chainValidationResult{
			OK:     true,
			Stage:  "chain_v2_validated",
			Reason: "verified code, tokens, reserves",
		}
	}

	return chainValidationResult{
		OK:     false,
		Stage:  "chain_state_unreadable",
		Reason: fmt.Sprintf("unable to read v3 or v2 state (slot0=%v liquidity=%v reserves=%v fee=%v)", slot0Err, liquidityErr, reservesErr, feeErr),
	}
}

func (app *App) rpcProviderForChain(chain domain.ChainID) *rpc.RoundRobinProvider {
	if app == nil || app.rpc == nil {
		return nil
	}
	return app.rpc[string(chain)]
}

func callAddressMethod(ctx context.Context, provider *rpc.RoundRobinProvider, contract domain.Address, signature string) (domain.Address, error) {
	data, err := callRawMethod(ctx, provider, contract, signature)
	if err != nil {
		return domain.Address{}, err
	}
	if len(data) < 32 {
		return domain.Address{}, fmt.Errorf("%s returned short response", signature)
	}
	return domain.ParseAddress(common.BytesToAddress(data[len(data)-20:]).Hex())
}

func callUintMethod(ctx context.Context, provider *rpc.RoundRobinProvider, contract domain.Address, signature string) (uint64, error) {
	data, err := callRawMethod(ctx, provider, contract, signature)
	if err != nil {
		return 0, err
	}
	if len(data) < 32 {
		return 0, fmt.Errorf("%s returned short response", signature)
	}
	n := new(big.Int).SetBytes(data[:32])
	if !n.IsUint64() {
		return 0, fmt.Errorf("%s returned non-uint64 value", signature)
	}
	return n.Uint64(), nil
}

func callRawMethod(ctx context.Context, provider *rpc.RoundRobinProvider, contract domain.Address, signature string) ([]byte, error) {
	selector := crypto.Keccak256([]byte(signature))[:4]
	to := common.HexToAddress(contract.String())
	return provider.CallContract(ctx, ethereum.CallMsg{
		To:   &to,
		Data: selector,
	}, nil)
}

func normalizeV3FeeToBPS(raw uint64) uint {
	if raw == 0 {
		return 0
	}
	if raw < 100 {
		return uint(raw)
	}
	return uint(raw / 100)
}
