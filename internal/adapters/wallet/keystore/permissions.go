//go:build !disable_wallet

package keystore

import (
	"fmt"
	"os"
)

// ErrPermissionsTooOpen is returned when keystore file permissions are too permissive.
var ErrPermissionsTooOpen = fmt.Errorf("keystore permissions too open")

// CheckFilePermissions verifies that a keystore file has secure permissions (0600).
// Files with permissions allowing group or other access (0o077) are rejected.
//
// This check prevents other users on a shared system from reading the keystore.
// On Unix-like systems, this checks that the file mode has no permissions for
// group (g) or others (o).
//
// Parameters:
//   - path: Path to the keystore file to check
//
// Returns:
//   - nil if permissions are secure (0600)
//   - ErrPermissionsTooOpen if permissions allow group/other access
//   - any other error if the file cannot be accessed
func CheckFilePermissions(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}

	mode := info.Mode().Perm()
	// Check if any bits are set for group or others (0o077 mask)
	if mode&0o077 != 0 {
		return fmt.Errorf("%w: %s permissions %o too open, must be 0600", ErrPermissionsTooOpen, path, mode)
	}

	return nil
}