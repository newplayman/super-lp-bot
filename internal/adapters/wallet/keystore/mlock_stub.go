//go:build !disable_wallet && !linux

package keystore

// mlock stubs for non-Linux platforms.
// Memory locking is only supported on Linux.
func mlock(b []byte) error {
	return nil
}

// munlock stubs for non-Linux platforms.
func munlock(b []byte) error {
	return nil
}