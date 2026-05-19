package domain

// AuditVerdict is the overall audit result.
type AuditVerdict string

const (
	AuditPass AuditVerdict = "pass"
	AuditWarn AuditVerdict = "warn"
	AuditFail AuditVerdict = "fail"
)

// AuditCategory is a category of audit check.
type AuditCategory string

const (
	AuditHoneypot        AuditCategory = "honeypot"
	AuditOwnerMint       AuditCategory = "owner_mint"
	AuditProxy           AuditCategory = "proxy"
	AuditBlacklist       AuditCategory = "blacklist"
	AuditFeeOnTransfer   AuditCategory = "fee_on_transfer"
	AuditRugSimilarity   AuditCategory = "rug_similarity"
	AuditLPNotLocked     AuditCategory = "lp_not_locked"
	AuditLPConcentration AuditCategory = "lp_concentration"
	AuditDeployerHistory AuditCategory = "deployer_history"
)

// AuditFinding is a single audit check result.
type AuditFinding struct {
	Category AuditCategory
	Verdict  AuditVerdict
	Score    float64  // 0–100 risk score for this check
	Message  string
	Details  string   // raw findings
}

// AuditReport is a collection of findings for a pool.
type AuditReport struct {
	PoolID    string
	Chain     ChainID
	Findings  []AuditFinding
	Verdict   AuditVerdict // overall verdict
	RiskScore float64      // overall risk score (0 = safe, 100 = dangerous)
	Timestamp int64
}

// OverallVerdict computes the worst verdict across all findings.
func (r AuditReport) OverallVerdict() AuditVerdict {
	for _, f := range r.Findings {
		if f.Verdict == AuditFail {
			return AuditFail
		}
	}
	for _, f := range r.Findings {
		if f.Verdict == AuditWarn {
			return AuditWarn
		}
	}
	return AuditPass
}

// MaxScore returns the maximum risk score across all findings.
func (r AuditReport) MaxScore() float64 {
	var max float64
	for _, f := range r.Findings {
		if f.Score > max {
			max = f.Score
		}
	}
	return max
}
