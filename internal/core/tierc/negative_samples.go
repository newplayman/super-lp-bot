package tierc

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"

	"github.com/lpbot/lpbot/internal/domain"
)

const DefaultNegativeSamplesPath = "configs/tierc_negative_samples.json"

type NegativeSample struct {
	ID      string   `json:"id"`
	PoolIDs []string `json:"pool_ids"`
	Tokens  []string `json:"tokens"`
	Reason  string   `json:"reason,omitempty"`
}

type negativeSamplesFile struct {
	UpdatedAt string           `json:"updated_at,omitempty"`
	Samples   []NegativeSample `json:"samples"`
}

type negativeSampleMatcher struct {
	byPoolID map[string]NegativeSample
	byToken  map[string]NegativeSample
}

var (
	negativeSamplesOnce    sync.Once
	negativeSamplesMatcher negativeSampleMatcher
)

func loadNegativeSampleMatcher() negativeSampleMatcher {
	negativeSamplesOnce.Do(func() {
		path := strings.TrimSpace(os.Getenv("LPBOT_TIERC_NEGATIVE_SAMPLES_PATH"))
		usingDefaultPath := path == ""
		if path == "" {
			path = DefaultNegativeSamplesPath
		}
		raw, err := readNegativeSampleFile(path, usingDefaultPath)
		if err != nil {
			negativeSamplesMatcher = negativeSampleMatcher{byPoolID: map[string]NegativeSample{}, byToken: map[string]NegativeSample{}}
			return
		}
		var payload negativeSamplesFile
		if err := json.Unmarshal(raw, &payload); err != nil {
			negativeSamplesMatcher = negativeSampleMatcher{byPoolID: map[string]NegativeSample{}, byToken: map[string]NegativeSample{}}
			return
		}
		matcher := negativeSampleMatcher{
			byPoolID: make(map[string]NegativeSample, len(payload.Samples)),
			byToken:  make(map[string]NegativeSample, len(payload.Samples)),
		}
		for _, sample := range payload.Samples {
			for _, poolID := range sample.PoolIDs {
				if normalized := strings.ToLower(strings.TrimSpace(poolID)); normalized != "" {
					matcher.byPoolID[normalized] = sample
				}
			}
			for _, token := range sample.Tokens {
				if normalized := strings.ToLower(strings.TrimSpace(token)); normalized != "" {
					matcher.byToken[normalized] = sample
				}
			}
		}
		negativeSamplesMatcher = matcher
	})
	return negativeSamplesMatcher
}

func readNegativeSampleFile(path string, usingDefaultPath bool) ([]byte, error) {
	candidates := uniqueCandidateNegativeSamplePaths(path)
	if usingDefaultPath {
		if fallback := resolvePathFromSourceRoot(DefaultNegativeSamplesPath); fallback != "" {
			candidates = append(candidates, fallback)
		}
	}
	candidates = uniqueStrings(candidates)

	var lastErr error
	for _, candidate := range candidates {
		raw, err := os.ReadFile(candidate)
		if err == nil {
			return raw, nil
		}
		lastErr = fmt.Errorf("read negative sample file: %w", err)
	}
	return nil, lastErr
}

func resolvePathFromSourceRoot(relativePath string) string {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		return ""
	}
	relativePath = filepath.FromSlash(strings.TrimSpace(relativePath))
	if relativePath == "" {
		return ""
	}
	dir := filepath.Dir(currentFile)
	for depth := 0; depth < 10; depth++ {
		candidate := filepath.Clean(filepath.Join(dir, relativePath))
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return ""
}

func uniqueCandidateNegativeSamplePaths(path string) []string {
	clean := filepath.FromSlash(strings.TrimSpace(path))
	candidates := []string{clean}
	if filepath.IsAbs(clean) {
		return candidates
	}
	if abs, err := filepath.Abs(clean); err == nil {
		candidates = append(candidates, abs)
	}
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(cwd, clean))
	}
	return candidates
}

func uniqueStrings(input []string) []string {
	seen := make(map[string]struct{}, len(input))
	task := make([]string, 0, len(input))
	for _, value := range input {
		key := filepath.Clean(value)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		task = append(task, key)
	}
	return task
}

func knownNegativeSample(pool domain.Pool) (NegativeSample, bool) {
	matcher := loadNegativeSampleMatcher()
	if sample, ok := matcher.byPoolID[strings.ToLower(strings.TrimSpace(pool.ID))]; ok {
		return sample, true
	}
	if sample, ok := matcher.byToken[strings.ToLower(strings.TrimSpace(pool.Token0.String()))]; ok {
		return sample, true
	}
	if sample, ok := matcher.byToken[strings.ToLower(strings.TrimSpace(pool.Token1.String()))]; ok {
		return sample, true
	}
	return NegativeSample{}, false
}
