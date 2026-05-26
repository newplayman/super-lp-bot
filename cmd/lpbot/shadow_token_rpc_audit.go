package main

import (
	"context"
	"bytes"
	"encoding/csv"
	"fmt"
	"math/big"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/lpbot/lpbot/internal/adapters/rpc"
	"github.com/lpbot/lpbot/internal/domain"
)

type shadowTokenAuditInputRow struct {
	TokenSymbol  string
	TokenAddress string
	Chain        string
}

type shadowTokenAuditOutputRow struct {
	TokenSymbol       string
	TokenAddress      string
	Chain             string
	HasBytecode       string
	DecimalsResult    string
	DecimalsError     string
	SymbolResult      string
	SymbolError       string
	MetadataUntrusted string
}

func (app *App) generateShadowTokenRPCAudit(ctx context.Context, inputPath string, outputPath string) error {
	inputRows, err := readShadowTokenAuditInput(inputPath)
	if err != nil {
		return err
	}
	outputRows := make([]shadowTokenAuditOutputRow, 0, len(inputRows))
	for _, row := range inputRows {
		outputRows = append(outputRows, app.auditShadowTokenMetadata(ctx, row))
	}
	if err := writeShadowTokenAuditOutput(outputPath, outputRows); err != nil {
		return err
	}
	return nil
}

func readShadowTokenAuditInput(path string) ([]shadowTokenAuditInputRow, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open shadow token audit input: %w", err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("read shadow token audit input csv: %w", err)
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("shadow token audit input is empty")
	}

	header := make(map[string]int, len(rows[0]))
	for idx, name := range rows[0] {
		header[strings.ToLower(strings.TrimSpace(name))] = idx
	}
	if _, ok := header["token_address"]; !ok {
		return nil, fmt.Errorf("shadow token audit input requires token_address column")
	}

	results := make([]shadowTokenAuditInputRow, 0, len(rows)-1)
	for _, record := range rows[1:] {
		if len(record) == 0 {
			continue
		}
		tokenAddress := csvField(record, header, "token_address")
		if tokenAddress == "" {
			continue
		}
		results = append(results, shadowTokenAuditInputRow{
			TokenSymbol:  csvField(record, header, "token_symbol"),
			TokenAddress: tokenAddress,
			Chain:        csvField(record, header, "chain"),
		})
	}
	return results, nil
}

func writeShadowTokenAuditOutput(path string, rows []shadowTokenAuditOutputRow) error {
	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create shadow token audit output: %w", err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	if err := writer.Write([]string{
		"token_symbol",
		"token_address",
		"chain",
		"has_bytecode",
		"decimals_result",
		"decimals_error",
		"symbol_result",
		"symbol_error",
		"metadata_untrusted",
	}); err != nil {
		return fmt.Errorf("write shadow token audit header: %w", err)
	}

	for _, row := range rows {
		if err := writer.Write([]string{
			row.TokenSymbol,
			row.TokenAddress,
			row.Chain,
			row.HasBytecode,
			row.DecimalsResult,
			row.DecimalsError,
			row.SymbolResult,
			row.SymbolError,
			row.MetadataUntrusted,
		}); err != nil {
			return fmt.Errorf("write shadow token audit row: %w", err)
		}
	}
	return writer.Error()
}

func (app *App) auditShadowTokenMetadata(ctx context.Context, input shadowTokenAuditInputRow) shadowTokenAuditOutputRow {
	output := shadowTokenAuditOutputRow{
		TokenSymbol:       strings.TrimSpace(input.TokenSymbol),
		TokenAddress:      strings.TrimSpace(input.TokenAddress),
		Chain:             normalizeShadowAuditChain(input.Chain),
		HasBytecode:       "no",
		MetadataUntrusted: "yes",
	}

	tokenAddress, err := domain.ParseAddress(output.TokenAddress)
	if err != nil {
		output.DecimalsError = fmt.Sprintf("invalid token address: %v", err)
		output.SymbolError = fmt.Sprintf("invalid token address: %v", err)
		return output
	}

	provider := app.rpcProviderForChain(shadowAuditChainID(output.Chain))
	if provider == nil {
		output.DecimalsError = fmt.Sprintf("rpc provider unavailable for chain %s", output.Chain)
		output.SymbolError = fmt.Sprintf("rpc provider unavailable for chain %s", output.Chain)
		return output
	}

	code, codeErr := provider.CodeAt(ctx, tokenAddress, nil)
	if codeErr != nil {
		output.DecimalsError = fmt.Sprintf("code lookup failed: %v", codeErr)
		output.SymbolError = fmt.Sprintf("code lookup failed: %v", codeErr)
		return output
	}
	if len(code) == 0 {
		output.DecimalsError = "no bytecode at address"
		output.SymbolError = "no bytecode at address"
		return output
	}
	output.HasBytecode = "yes"

	if decimals, err := tokenDecimals(ctx, provider, tokenAddress); err != nil {
		output.DecimalsError = err.Error()
	} else {
		output.DecimalsResult = fmt.Sprintf("%d", decimals)
	}

	if symbol, err := shadowAuditTokenSymbol(ctx, provider, tokenAddress); err != nil {
		output.SymbolError = err.Error()
	} else {
		output.SymbolResult = symbol
	}

	if output.DecimalsError == "" && output.SymbolError == "" && output.HasBytecode == "yes" {
		output.MetadataUntrusted = "no"
	}
	return output
}

func csvField(record []string, header map[string]int, key string) string {
	idx, ok := header[key]
	if !ok || idx < 0 || idx >= len(record) {
		return ""
	}
	return strings.TrimSpace(record[idx])
}

func normalizeShadowAuditChain(value string) string {
	normalized := strings.ToLower(strings.TrimSpace(value))
	if normalized == "" {
		return "base"
	}
	return normalized
}

func shadowAuditChainID(value string) domain.ChainID {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "solana":
		return domain.ChainSolana
	default:
		return domain.ChainBase
	}
}

func shadowAuditTokenSymbol(ctx context.Context, provider *rpc.RoundRobinProvider, token domain.Address) (string, error) {
	raw, err := callRawMethod(ctx, provider, token, "symbol()")
	if err != nil {
		return "", err
	}
	return decodeERC20StringResult(raw)
}

func decodeERC20StringResult(data []byte) (string, error) {
	if len(data) == 0 {
		return "", fmt.Errorf("empty response")
	}
	if dynamic, ok := decodeDynamicABIString(data); ok {
		return dynamic, nil
	}
	if fixed, ok := decodeFixedABIString(data); ok {
		return fixed, nil
	}
	return "", fmt.Errorf("unrecognized ERC20 string encoding")
}

func decodeDynamicABIString(data []byte) (string, bool) {
	if len(data) < 64 {
		return "", false
	}
	offset := new(big.Int).SetBytes(data[:32])
	if !offset.IsUint64() || offset.Uint64() != 32 {
		return "", false
	}
	length := new(big.Int).SetBytes(data[32:64])
	if !length.IsUint64() {
		return "", false
	}
	size := int(length.Uint64())
	if size < 0 || 64+size > len(data) {
		return "", false
	}
	text := strings.TrimSpace(strings.TrimRight(string(data[64:64+size]), "\x00"))
	if text == "" || !utf8.ValidString(text) {
		return "", false
	}
	return text, true
}

func decodeFixedABIString(data []byte) (string, bool) {
	if len(data) < 32 {
		return "", false
	}
	word := data[:32]
	if idx := bytes.IndexByte(word, 0); idx >= 0 {
		word = word[:idx]
	}
	text := strings.TrimSpace(string(word))
	if text == "" || !utf8.ValidString(text) {
		return "", false
	}
	return text, true
}
