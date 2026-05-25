package main

import (
	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

type liveSubmissionSemantics interface {
	submissionStatus() domain.TxStatus
	confirmsOnSend() bool
}

func txStatusAfterLiveSend(broadcaster ports.Broadcaster, requiredConfs int) domain.TxStatus {
	if aware, ok := broadcaster.(liveSubmissionSemantics); ok {
		return aware.submissionStatus()
	}
	if requiredConfs > 0 {
		return domain.TxConfirmed
	}
	return domain.TxBroadcast
}

func broadcasterConfirmsOnSend(broadcaster ports.Broadcaster, requiredConfs int) bool {
	if aware, ok := broadcaster.(liveSubmissionSemantics); ok {
		return aware.confirmsOnSend()
	}
	return requiredConfs > 0
}
