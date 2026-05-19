package idgen

import "github.com/google/uuid"

func NewEventID() string { return uuid.Must(uuid.NewV7()).String() }

func NewTraceID(prefix string) string { return prefix + "-" + uuid.NewString()[:8] }