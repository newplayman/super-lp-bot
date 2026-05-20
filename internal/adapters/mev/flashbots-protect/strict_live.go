//go:build live

package flashbotsprotect

// This file sets build-time flags for the live build tag.
// When live tag is set, StrictMode is forced to true.

func init() {
	strictModeForLive = true
}
