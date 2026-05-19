// Package main aggregates Phase 0 backtest results into a single verdict.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"text/template"
)

type PoolResult struct {
	Chain    string
	Pool     string
	Verdict  string
	ErrorPct float64
	Summary  string
}

type AggregateResult struct {
	Total   int
	Passed  int
	Warned  int
	Failed  int
	Pools   []PoolResult
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: aggregate-verdict <output_dir>")
		os.Exit(1)
	}

	outputDir := os.Args[1]
	result := &AggregateResult{}

	// Find all verdict.md files
	entries, err := os.ReadDir(outputDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading output dir: %v\n", err)
		os.Exit(1)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		poolDir := filepath.Join(outputDir, entry.Name())
		verdictPath := filepath.Join(poolDir, "verdict.md")
		summaryPath := filepath.Join(poolDir, "summary.json")

		if _, err := os.Stat(verdictPath); os.IsNotExist(err) {
			continue
		}

		// Parse verdict
		poolResult := PoolResult{
			Chain: extractField(entry.Name(), "-", 0),
			Pool:  entry.Name(),
		}

		verdictContent, err := os.ReadFile(verdictPath)
		if err == nil {
			poolResult.Verdict = extractVerdict(string(verdictContent))
			poolResult.ErrorPct = extractErrorPct(string(verdictContent))
		}

		summaryContent, err := os.ReadFile(summaryPath)
		if err == nil {
			poolResult.Summary = string(summaryContent)
		}

		result.Pools = append(result.Pools, poolResult)
	}

	// Sort by chain then pool
	sort.Slice(result.Pools, func(i, j int) bool {
		if result.Pools[i].Chain != result.Pools[j].Chain {
			return result.Pools[i].Chain < result.Pools[j].Chain
		}
		return result.Pools[i].Pool < result.Pools[j].Pool
	})

	// Count results
	result.Total = len(result.Pools)
	for _, p := range result.Pools {
		switch p.Verdict {
		case "PASS":
			result.Passed++
		case "WARN":
			result.Warned++
		case "FAIL":
			result.Failed++
		default:
			result.Warned++
		}
	}

	// Generate markdown
	md := generateVerdictMarkdown(result)

	// Write to VERDICT-phase0.md
	verdictPath := filepath.Join(outputDir, "VERDICT-phase0.md")
	if err := os.WriteFile(verdictPath, []byte(md), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing verdict: %v\n", err)
		os.Exit(1)
	}

	// Also output JSON for machine parsing
	jsonPath := filepath.Join(outputDir, "verdict-summary.json")
	if enc, err := json.MarshalIndent(result, "", "  "); err == nil {
		os.WriteFile(jsonPath, enc, 0644)
	}

	fmt.Printf("Aggregate verdict written to: %s\n", verdictPath)
	fmt.Printf("Summary: %d total, %d passed, %d warned, %d failed\n",
		result.Total, result.Passed, result.Warned, result.Failed)

	if result.Failed > 0 {
		os.Exit(1)
	}
}

func extractField(s, sep string, idx int) string {
	parts := strings.Split(s, sep)
	if idx < len(parts) {
		return parts[idx]
	}
	return s
}

func extractVerdict(content string) string {
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "Verdict:") {
			return strings.TrimSpace(strings.TrimPrefix(line, "Verdict:"))
		}
	}
	return "UNKNOWN"
}

func extractErrorPct(content string) float64 {
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "Error:") {
			var pct float64
			fmt.Sscanf(line, "Error: %f%%", &pct)
			return pct
		}
	}
	return -1
}

func generateVerdictMarkdown(r *AggregateResult) string {
	tmpl := `# Phase 0 Acceptance Verdict

**Date:** {{.Date}}
**Total Pools:** {{.Total}}

## Summary

| Metric | Count |
|--------|-------|
| Passed (< 5%) | {{.Passed}} |
| Warning (5-10%) | {{.Warned}} |
| Failed (> 10%) | {{.Failed}} |

## Results

| Chain | Pool | Error % | Verdict |
|-------|------|---------|---------|
{{range .Pools}}| {{.Chain}} | {{.Pool}} | {{.ErrorPct}} | {{.Verdict}} |
{{end}}

## Verdict

{{if eq .Failed 0}}{{if eq .Warned 0}}**PASSED** - All pools within acceptable error range.
{{else}}**PASSED WITH WARNINGS** - {{.Warned}} pools exceed 5% error threshold.
{{end}}{{else}}**FAILED** - {{.Failed}} pools exceed 10% error threshold. Review required.
{{end}}

## Notes

- Error threshold: < 5% = PASS, 5-10% = WARN, > 10% = FAIL
- Ground truth sourced from DexScreener API
- Phase 0 uses fixture data (no real API calls)
`

	data := struct {
		Date    string
		Total   int
		Passed  int
		Warned  int
		Failed  int
		Pools   []PoolResult
	}{
		Date:   "2026-05-19",
		Total:  r.Total,
		Passed: r.Passed,
		Warned: r.Warned,
		Failed: r.Failed,
		Pools:  r.Pools,
	}

	var sb strings.Builder
	template.Must(template.New("verdict").Parse(tmpl)).Execute(&sb, data)
	return sb.String()
}