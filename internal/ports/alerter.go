// Package ports defines the hexagonal adapter interfaces for lp-bot.
//
// Alerter interfaces (this file):
//
//   - Alerter: send alerts to notification channels (Telegram, etc.)
//   - AlertLevel: alert severity levels (P0/P1/P2)
//
// See spec §7.4 (告警分级) and alert routing rules in config.
package ports

// AlertLevel represents the severity of an alert.
// Higher levels indicate more critical situations requiring immediate attention.
type AlertLevel string

const (
	// AlertP0 is the highest severity level for critical alerts.
	// P0 triggers: kill triggered, recon failed, dryrun broadcast > 0,
	// all RPC down, hot wallet gas < 1 day budget.
	// Channel: Telegram @lpbot_p0 (with sound).
	AlertP0 AlertLevel = "p0"

	// AlertP1 is the warning severity level.
	// P1 triggers: freeze triggered, single pool stop_loss, rug score
	// degradation, single RPC down, VaR > warn threshold.
	// Channel: Telegram @lpbot_p1 (silent).
	AlertP1 AlertLevel = "p1"

	// AlertP2 is the informational severity level.
	// P2 triggers: position opened/closed, rebalance, daily report.
	// Channel: Telegram @lpbot_info.
	AlertP2 AlertLevel = "p2"
)

// Alerter defines the interface for sending alerts to notification channels.
// Implementations handle routing to appropriate channels based on alert level.
//
// Alerter is typically used by the alertlog bus subscriber to route events
// matching configured alert rules. See spec §7.4 for alert routing configuration.
//
// Thread safety: implementations must be safe for concurrent use.
type Alerter interface {
	// SendAlert sends an alert at the specified severity level.
	//
	// Parameters:
	//   - level: the severity of the alert (P0/P1/P2)
	//   - src: the source component or module that generated the alert
	//   - msg: the alert message content
	//
	// The message may be formatted using templates defined in config.
	// Returns an error only if the alert cannot be sent; callers should
	// log errors but not retry failed alerts (to avoid spam during outages).
	//
	// Example usage:
	//   alerter.SendAlert(ports.AlertP0, "risk", "KILL: portfolio loss > 10%")
	SendAlert(level AlertLevel, src, msg string) error
}