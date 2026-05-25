package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/core/tierc"
)

var holderOverviewTop10Pattern = regexp.MustCompile(`(?is)Top\s*10\s*holders:\s*<strong>\s*([0-9]+(?:\.[0-9]+)?)%\s*</strong>`)

type holderSnapshotFileLocal struct {
	UpdatedAt string                     `json:"updated_at,omitempty"`
	Entries   []tierc.HolderSnapshotEntry `json:"entries"`
}

func runBaseTierCHolderSnapshotRefresh(ctx context.Context, path string) error {
	if strings.TrimSpace(path) == "" {
		path = tierc.DefaultHolderSnapshotPath
	}
	payload, err := loadHolderSnapshotFile(path)
	if err != nil {
		return err
	}
	client := &http.Client{Timeout: 20 * time.Second}
	updated := 0
	for i := range payload.Entries {
		entry := &payload.Entries[i]
		if strings.ToLower(strings.TrimSpace(entry.Chain)) != "base" {
			continue
		}
		if strings.TrimSpace(entry.Token) == "" {
			continue
		}
		pct, err := fetchBaseTokenTop10HolderPct(ctx, client, entry.Token)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: holder snapshot refresh failed token=%s: %v\n", entry.Token, err)
			continue
		}
		entry.Top10HolderPct = pct
		entry.Source = "basescan_manual_snapshot_refresh"
		updated++
	}
	sort.SliceStable(payload.Entries, func(i, j int) bool {
		return strings.ToLower(payload.Entries[i].Token) < strings.ToLower(payload.Entries[j].Token)
	})
	payload.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := writeHolderSnapshotFile(path, payload); err != nil {
		return err
	}
	fmt.Printf("base_tierc_holder_snapshot_refresh path=%s updated=%d total=%d\n", path, updated, len(payload.Entries))
	for _, entry := range payload.Entries {
		fmt.Printf("%s|%s|%s|%s\n", entry.Chain, entry.Token, entry.Top10HolderPct, entry.Source)
	}
	return nil
}

func loadHolderSnapshotFile(path string) (*holderSnapshotFileLocal, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read holder snapshot file: %w", err)
	}
	var payload holderSnapshotFileLocal
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, fmt.Errorf("decode holder snapshot file: %w", err)
	}
	return &payload, nil
}

func writeHolderSnapshotFile(path string, payload *holderSnapshotFileLocal) error {
	raw, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return fmt.Errorf("encode holder snapshot file: %w", err)
	}
	return os.WriteFile(path, append(raw, '\n'), 0644)
}

func fetchBaseTokenTop10HolderPct(ctx context.Context, client *http.Client, token string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://basescan.org/token/"+strings.TrimSpace(token), nil)
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read response: %w", err)
	}
	match := holderOverviewTop10Pattern.FindSubmatch(body)
	if len(match) != 2 {
		return "", fmt.Errorf("top 10 holders percentage not found")
	}
	return string(match[1]), nil
}
