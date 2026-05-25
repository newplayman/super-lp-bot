//go:build live

package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	solanago "github.com/gagliardetto/solana-go"
	solrpc "github.com/gagliardetto/solana-go/rpc"
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/platform/config"
)

func runSolanaLPCloseCanary(ctx context.Context, cfg *config.Config, maxPriorityLamports uint64) error {
	report, err := inspectExistingSolanaLPCloseCandidate(ctx, cfg, maxPriorityLamports)
	if err != nil {
		return err
	}
	printSolanaLPClosePreflight(report)
	if report.Position == nil {
		err := fmt.Errorf("solana lp close canary requires an existing open position")
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if strings.TrimSpace(report.Blocker) != "" {
		err := fmt.Errorf("solana lp close canary blocked: %s", report.Blocker)
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !report.CloseCandidate {
		err := fmt.Errorf("solana lp close canary requires exit_now signal; got action=%s reason=%s", report.Metadata.ExitAction, report.Metadata.ExitReason)
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !strings.EqualFold(strings.TrimSpace(report.Protocol), "pancakeswap-v3-solana") {
		err := fmt.Errorf("solana lp close canary unsupported protocol %s", report.Protocol)
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !report.CloseBuildReady {
		err := fmt.Errorf("solana_pancakeswap_v3_solana_close_position_build_not_ready")
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !report.CloseSignReady {
		err := fmt.Errorf("solana_pancakeswap_v3_solana_close_position_sign_not_ready")
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !report.DecreaseSimReady {
		reason := strings.TrimSpace(report.DecreaseBlocker)
		if reason == "" {
			reason = "decrease_liquidity_not_ready"
		}
		err := fmt.Errorf("solana_pancakeswap_v3_solana_decrease_liquidity_not_ready: %s", reason)
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !report.CollectSimReady {
		reason := strings.TrimSpace(report.CollectBlocker)
		if reason == "" {
			reason = "collect_fees_not_ready"
		}
		err := fmt.Errorf("solana_pancakeswap_v3_solana_collect_fees_not_ready: %s", reason)
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	key, keySource, ok, err := loadSolanaPrivateKeyFromEnv()
	if err != nil {
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	if !ok {
		err := fmt.Errorf("missing signer env: SOLANA_PRIVATE_KEY|SOLANA_KEYPAIR_JSON|SOLANA_KEYPAIR_PATH")
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "gate", err.Error())
		return err
	}
	walletPubkey := key.PublicKey()
	client := solrpc.New(solanaReadinessEndpoint(cfg))
	state, err := newCanaryEventWriter(ctx, cfg)
	if err != nil {
		return err
	}
	defer state.Close()

	decreaseSig := ""
	if strings.TrimSpace(report.Metadata.PositionLiquidityRaw) != "0" {
		decreaseBuild, err := buildPancakeSolanaDecreaseLiquidityTransaction(ctx, cfg, report.Position.TokenID, report.PoolID, walletPubkey)
		if err != nil {
			_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "decrease_build", err.Error())
			return err
		}
		decreaseBytes := []byte(nil)
		decreaseSig, decreaseBytes, err = refreshSignAndSimulatePancakeDecrease(ctx, client, decreaseBuild.Tx, key)
		if err != nil {
			_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "decrease_sim", err.Error())
			return err
		}
		decreaseTx := solanaLPExitSignedTx(report, walletPubkey.String(), "solana-lp-close-decrease-"+decreaseSig, decreaseSig, decreaseBytes, report.PoolID)
		if err := recordSolanaLPExitTx(ctx, state, report, decreaseTx, "decrease_signed", keySource, "signed Pancake Solana decrease-liquidity"); err != nil {
			return err
		}
		if err := sendAndConfirmSolanaLPExitTx(ctx, cfg, client, decreaseBuild.Tx, decreaseSig); err != nil {
			_ = recordSolanaLPExitTx(ctx, state, report, decreaseTx, "decrease_broadcast_failed", keySource, err.Error())
			_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "decrease_broadcast", err.Error())
			return err
		}
		if err := state.RecordSignedTx(ctx, decreaseTx, domain.TxBroadcast); err != nil {
			return err
		}
		if err := recordSolanaLPExitTx(ctx, state, report, decreaseTx, "decrease_broadcast", keySource, "broadcast Pancake Solana decrease-liquidity"); err != nil {
			return err
		}
		fmt.Printf("solana_lp_close_canary_decrease_broadcast success=true signature=%s liquidity_raw=%s\n", decreaseSig, decreaseBuild.LiquidityRaw)
	} else {
		fmt.Printf("solana_lp_close_canary_decrease_skip reason=zero_liquidity position_id=%s\n", shortAddress(report.Position.ID))
	}

	closeBuild, err := buildPancakeSolanaClosePositionTransaction(ctx, cfg, report.Position.TokenID, report.PoolID, walletPubkey)
	if err != nil {
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "close_build_after_decrease", err.Error())
		return err
	}
	closeSig, closeBytes, err := refreshSignAndSimulatePancakeClose(ctx, client, closeBuild.Tx, key)
	if err != nil {
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "close_sim_after_decrease", err.Error())
		return err
	}
	closeTx := solanaLPExitSignedTx(report, walletPubkey.String(), "solana-lp-close-position-"+closeSig, closeSig, closeBytes, report.Position.TokenID)
	if err := recordSolanaLPExitTx(ctx, state, report, closeTx, "close_signed", keySource, "signed Pancake Solana close-position"); err != nil {
		return err
	}
	if err := sendAndConfirmSolanaLPExitTx(ctx, cfg, client, closeBuild.Tx, closeSig); err != nil {
		_ = recordSolanaLPExitTx(ctx, state, report, closeTx, "close_broadcast_failed", keySource, err.Error())
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "close_broadcast", err.Error())
		return err
	}
	if err := state.RecordSignedTx(ctx, closeTx, domain.TxBroadcast); err != nil {
		return err
	}
	if err := recordSolanaLPExitTx(ctx, state, report, closeTx, "close_broadcast", keySource, "broadcast Pancake Solana close-position"); err != nil {
		return err
	}
	if _, err := state.db.ExecContext(ctx, `
		UPDATE positions
		SET status = $1,
		    closed_at = CASE WHEN closed_at = 0 THEN $2 ELSE closed_at END
		WHERE id = $3
	`, string(domain.StatusClosed), time.Now().Unix(), report.Position.ID); err != nil {
		_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "persist_closed", err.Error())
		return err
	}
	_ = recordSolanaLPCloseInspection(ctx, cfg, report, "solana_lp_close_canary", "complete", "")
	fmt.Printf("solana_lp_close_canary_complete success=true decrease_signature=%s close_signature=%s position_id=%s\n", decreaseSig, closeSig, shortAddress(report.Position.ID))
	return nil
}

func refreshSignAndSimulatePancakeDecrease(ctx context.Context, client *solrpc.Client, tx *solanago.Transaction, key solanago.PrivateKey) (string, []byte, error) {
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentProcessed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return "", nil, fmt.Errorf("refresh solana decrease blockhash: %w", err)
	}
	refreshSolanaTransactionBlockhash(tx, blockhashResp.Value.Blockhash)
	signature, err := signPancakeSolanaDecreaseLiquidityTransaction(tx, key)
	if err != nil {
		return "", nil, err
	}
	if err := simulateSignedSolanaLPExitTx(ctx, client, tx, "decrease"); err != nil {
		return "", nil, err
	}
	bytes, err := tx.MarshalBinary()
	if err != nil {
		return "", nil, fmt.Errorf("marshal solana decrease tx: %w", err)
	}
	return signature, bytes, nil
}

func refreshSignAndSimulatePancakeClose(ctx context.Context, client *solrpc.Client, tx *solanago.Transaction, key solanago.PrivateKey) (string, []byte, error) {
	blockhashResp, err := client.GetLatestBlockhash(ctx, solrpc.CommitmentProcessed)
	if err != nil || blockhashResp == nil || blockhashResp.Value == nil {
		return "", nil, fmt.Errorf("refresh solana close blockhash: %w", err)
	}
	refreshSolanaTransactionBlockhash(tx, blockhashResp.Value.Blockhash)
	signature, err := signPancakeSolanaClosePositionTransaction(tx, key)
	if err != nil {
		return "", nil, err
	}
	if err := simulateSignedSolanaLPExitTx(ctx, client, tx, "close"); err != nil {
		return "", nil, err
	}
	bytes, err := tx.MarshalBinary()
	if err != nil {
		return "", nil, fmt.Errorf("marshal solana close tx: %w", err)
	}
	return signature, bytes, nil
}

func simulateSignedSolanaLPExitTx(ctx context.Context, client *solrpc.Client, tx *solanago.Transaction, stage string) error {
	simResp, simErr := client.SimulateTransactionWithOpts(ctx, tx, &solrpc.SimulateTransactionOpts{
		SigVerify:              false,
		Commitment:             solrpc.CommitmentProcessed,
		ReplaceRecentBlockhash: false,
	})
	if simErr != nil {
		return fmt.Errorf("simulate solana lp %s tx: %w", stage, simErr)
	}
	if simResp == nil || simResp.Value == nil {
		return fmt.Errorf("simulate solana lp %s tx returned empty response", stage)
	}
	if simResp.Value.Err != nil {
		return fmt.Errorf("simulate solana lp %s tx rejected: %v", stage, simResp.Value.Err)
	}
	fmt.Printf("solana_lp_close_canary_%s_simulation ready=true units=%d logs=%d\n", stage, derefUint64(simResp.Value.UnitsConsumed), len(simResp.Value.Logs))
	return nil
}

func sendAndConfirmSolanaLPExitTx(ctx context.Context, cfg *config.Config, client *solrpc.Client, tx *solanago.Transaction, expectedSignature string) error {
	txSig, err := client.SendTransactionWithOpts(ctx, tx, solrpc.TransactionOpts{
		SkipPreflight:       cfg.Chains.Solana.SkipPreflight,
		PreflightCommitment: solrpc.CommitmentProcessed,
	})
	if err != nil {
		return err
	}
	if txSig.String() != expectedSignature {
		return fmt.Errorf("solana lp exit signature mismatch after send: built=%s sent=%s", expectedSignature, txSig.String())
	}
	return waitForDirectSolanaConfirmation(ctx, client, txSig)
}

func solanaLPExitSignedTx(report solanaLPClosePreflight, from string, id string, signature string, txBytes []byte, to string) domain.SignedTx {
	return domain.SignedTx{
		UnsignedTx: domain.UnsignedTx{
			ID:     id,
			Chain:  domain.ChainSolana,
			From:   domain.MustParseAddress(from),
			To:     domain.MustParseAddress(to),
			MinOut: domain.ZeroDecimal(),
		},
		Signature: txBytes,
		Hash:      signature,
		Status:    domain.TxBuilt,
	}
}

func recordSolanaLPExitTx(ctx context.Context, state *canaryEventWriter, report solanaLPClosePreflight, tx domain.SignedTx, stage string, keySource string, message string) error {
	status := "ok"
	errorMsg := ""
	if strings.Contains(stage, "failed") {
		status = "blocked"
		errorMsg = message
	}
	if err := state.Record(ctx, canaryEvent{
		Chain:      domain.ChainSolana.String(),
		Command:    "solana_lp_close_canary",
		Stage:      stage,
		Status:     status,
		PositionID: report.Position.ID,
		PoolID:     report.PoolID,
		Wallet:     tx.From.String(),
		TokenID:    report.Position.TokenID,
		TxHash:     tx.Hash,
		AmountUSD:  report.Position.AmountUSD.String(),
		Message:    fmt.Sprintf("%s source=%s", message, keySource),
		ErrorMsg:   errorMsg,
		CreatedAt:  time.Now().Unix(),
	}); err != nil {
		return err
	}
	if status == "ok" && strings.Contains(stage, "signed") {
		return state.RecordSignedTx(ctx, tx, domain.TxBuilt)
	}
	return nil
}
