//go:build !disable_wallet

package keystore

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
)

// TestKeystore_Permissions_0600_OK verifies that a keystore file with 0600 permissions passes validation.
func TestKeystore_Permissions_0600_OK(t *testing.T) {
	// Create a temp file with 0600 permissions
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "test_key")
	err := os.WriteFile(tmpFile, []byte("test"), 0600)
	assert.NoError(t, err)

	err = CheckFilePermissions(tmpFile)
	assert.NoError(t, err, "0600 permissions should pass validation")
}

// TestKeystore_Permissions_0644_Reject verifies that a keystore file with 0644 permissions is rejected.
func TestKeystore_Permissions_0644_Reject(t *testing.T) {
	// Create a temp file with 0644 permissions (too open)
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "test_key")
	err := os.WriteFile(tmpFile, []byte("test"), 0644)
	assert.NoError(t, err)

	err = CheckFilePermissions(tmpFile)
	assert.Error(t, err, "0644 permissions should be rejected")
	assert.Contains(t, err.Error(), "permissions too open")
}

// TestKeystore_Permissions_0640_Reject verifies that a keystore file with 0640 permissions is rejected.
func TestKeystore_Permissions_0640_Reject(t *testing.T) {
	// Create a temp file with 0640 permissions (group readable)
	tmpDir := t.TempDir()
	tmpFile := filepath.Join(tmpDir, "test_key")
	err := os.WriteFile(tmpFile, []byte("test"), 0640)
	assert.NoError(t, err)

	err = CheckFilePermissions(tmpFile)
	assert.Error(t, err, "0640 permissions should be rejected")
	assert.Contains(t, err.Error(), "permissions too open")
}

// TestKeystore_Permissions_NonExistent verifies that checking permissions on a non-existent file returns an error.
func TestKeystore_Permissions_NonExistent(t *testing.T) {
	err := CheckFilePermissions("/nonexistent/path/to/key")
	assert.Error(t, err)
}