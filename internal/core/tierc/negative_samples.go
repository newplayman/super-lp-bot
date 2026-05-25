package tierc

import (
	"encoding/json"
	"os"
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
		if path == "" {
			path = DefaultNegativeSamplesPath
		}
		raw, err := os.ReadFile(path)
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
