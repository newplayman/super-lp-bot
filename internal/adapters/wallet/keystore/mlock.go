//go:build !disable_wallet && linux

package keystore

import (
	"golang.org/x/sys/unix"
)

// mlock locks memory to prevent swapping to disk.
// This protects sensitive key material from being written to swap space.
func mlock(b []byte) error {
	return unix.Mlock(b)
}

// munlock unlocks memory.
func munlock(b []byte) error {
	return unix.Munlock(b)
}