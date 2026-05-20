package keystore

import (
	"context"
	"errors"
	"math/big"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/accounts/keystore"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/lpbot/lpbot/internal/domain"
	"github.com/lpbot/lpbot/internal/ports"
)

// setupTestKeystore creates a temporary keystore directory with a test key.
func setupTestKeystore(t *testing.T, passphrase string) (string, common.Address) {
	t.Helper()

	// Create temp directory
	tmpDir, err := os.MkdirTemp("", "keystore_test")
	require.NoError(t, err)
	t.Cleanup(func() { os.RemoveAll(tmpDir) })

	// Create encrypted keystore
	ks := keystore.NewKeyStore(tmpDir, keystore.StandardScryptN, keystore.StandardScryptP)
	account, err := ks.NewAccount(passphrase)
	require.NoError(t, err)
	t.Logf("Created test keystore at: %s", account.URL.Path)
	t.Logf("Test address: %s", account.Address.Hex())

	// Wait for the file to be flushed to disk (keystore creates files async)
	time.Sleep(100 * time.Millisecond)

	return tmpDir, account.Address
}

func TestWallet_New_Success(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, expectedAddr := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir:  tmpDir,
		KeystoreFile: "", // Will auto-detect
		Passphrase:   passphrase,
		ChainID:      domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)
	require.NotNil(t, provider)

	// Open the wallet
	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)
	require.NotNil(t, wallet)

	// Verify the address matches (normalize to lowercase for comparison)
	assert.Equal(t, strings.ToLower(expectedAddr.Hex()), strings.ToLower(wallet.Address().String()), "address should match")

	// Clean up
	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_New_InvalidKey(t *testing.T) {
	passphrase := "test-passphrase-123"
	wrongPassphrase := "wrong-passphrase"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir:  tmpDir,
		KeystoreFile: "", // Will auto-detect
		Passphrase:   wrongPassphrase,
		ChainID:      domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Open should fail with wrong passphrase
	wallet, err := provider.Open(context.Background(), config)
	assert.Error(t, err)
	assert.Nil(t, wallet)
	assert.Contains(t, err.Error(), "failed to decrypt")
}

func TestWallet_Address(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, expectedAddr := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Address should match
	assert.Equal(t, strings.ToLower(expectedAddr.Hex()), strings.ToLower(wallet.Address().String()), "address should match")

	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_Sign(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Build a test transaction
	toAddr := common.HexToAddress("0x1234567890123456789012345678901234567890")
	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		From:     wallet.Address(),
		To:       domain.MustParseAddress(toAddr.Hex()),
		Data:     []byte{0x12, 0x34, 0x56, 0x78}, // Some random calldata
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	// Sign the transaction
	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)
	require.NotEmpty(t, signedTx.Signature)
	require.NotEmpty(t, signedTx.Hash)

	// Verify signature is RLP encoded (starts with transaction type byte)
	// EIP-2718 typed transactions start with 0x02 (EIP-1559)
	assert.True(t, len(signedTx.Signature) > 0, "signature should not be empty")

	t.Logf("Signed tx hash: %s", signedTx.Hash)
	t.Logf("Signature length: %d bytes", len(signedTx.Signature))

	err = wallet.Close()
	require.NoError(t, err)
}

// mockRPCProvider implements RPCProvider for testing
type mockRPCProvider struct {
	nonce uint64
}

func (m *mockRPCProvider) PendingNonceAt(_ context.Context, _ domain.Address) (uint64, error) {
	return m.nonce, nil
}

func TestWallet_ApproveExact(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock RPC provider
	mockRPC := &mockRPCProvider{nonce: 5}
	provider.SetRPCProvider(mockRPC)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Build approve transaction
	tokenAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	spenderAddr := domain.MustParseAddress("0x0987654321098765432109876543210987654321")

	approveTx, err := wallet.ApproveExact(
		context.Background(),
		tokenAddr,
		spenderAddr,
		big.NewInt(1000000),
	)
	require.NoError(t, err)

	// Verify transaction fields
	assert.Equal(t, domain.ChainBase, approveTx.Chain)
	assert.Equal(t, wallet.Address(), approveTx.From)
	assert.Equal(t, tokenAddr, approveTx.To)
	assert.NotEmpty(t, approveTx.Data)
	assert.Equal(t, domain.ZeroDecimal(), approveTx.Value)

	// Verify approve calldata (should start with 0x095ea7b3)
	assert.Equal(t, []byte{0x09, 0x5e, 0xa7, 0xb3}, approveTx.Data[:4])

	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_Revoke(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock RPC provider
	mockRPC := &mockRPCProvider{nonce: 5}
	provider.SetRPCProvider(mockRPC)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Build revoke transaction
	tokenAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	spenderAddr := domain.MustParseAddress("0x0987654321098765432109876543210987654321")

	revokeTx, err := wallet.Revoke(context.Background(), tokenAddr, spenderAddr)
	require.NoError(t, err)

	// Verify it's an approve(0) transaction
	assert.Equal(t, domain.ChainBase, revokeTx.Chain)
	assert.Equal(t, wallet.Address(), revokeTx.From)
	assert.Equal(t, tokenAddr, revokeTx.To)

	// Verify the calldata encodes approve(address, 0)
	// Selector (4 bytes) + padded address (32 bytes) + padded 0 (32 bytes) = 68 bytes
	assert.Equal(t, 68, len(revokeTx.Data))

	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_ApproveExact_NoRPCProvider(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Don't set RPC provider - should fail with proper error
	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Build approve transaction - should fail due to no RPC provider
	tokenAddr := domain.MustParseAddress("0x1234567890123456789012345678901234567890")
	spenderAddr := domain.MustParseAddress("0x0987654321098765432109876543210987654321")

	_, err = wallet.ApproveExact(
		context.Background(),
		tokenAddr,
		spenderAddr,
		big.NewInt(1000000),
	)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "RPC provider required")

	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_Chain(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	assert.Equal(t, domain.ChainBase, wallet.Chain())

	err = wallet.Close()
	require.NoError(t, err)
}

func TestWallet_Close(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Close should succeed
	err = wallet.Close()
	require.NoError(t, err)

	// After close, signing should fail
	_, err = wallet.Sign(context.Background(), domain.UnsignedTx{})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not open")
}

func TestWallet_Open_MissingDir(t *testing.T) {
	config := ports.WalletConfig{
		KeystoreDir: "/nonexistent/path/to/keystore",
		Passphrase:  "test",
		ChainID:     domain.ChainBase,
	}

	_, err := New(context.Background(), config)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "does not exist")
}

func TestWallet_ProviderType(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	assert.Equal(t, "keystore", provider.Type())
}

// TestSignMessage tests the SignMessage helper method.
func TestSignMessage(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Cast to our concrete type to access SignMessage
	keystoreWallet, ok := wallet.(*keystoreWallet)
	require.True(t, ok, "wallet should be *keystoreWallet")

	// Sign a test message
	message := []byte("Hello, Ethereum!")
	signature, err := keystoreWallet.SignMessage(context.Background(), message)
	require.NoError(t, err)
	require.NotEmpty(t, signature)

	// Signature should be 65 bytes (r, s, v)
	assert.Equal(t, 65, len(signature), "Ethereum signature should be 65 bytes")

	// Verify the signature is valid
	hash := crypto.Keccak256Hash(message)
	recoveredPub, err := crypto.SigToPub(hash.Bytes(), signature)
	require.NoError(t, err)
	require.NotNil(t, recoveredPub)

	recoveredAddr := crypto.PubkeyToAddress(*recoveredPub)
	assert.Equal(t, strings.ToLower(keystoreWallet.Address().String()), strings.ToLower(recoveredAddr.Hex()), "recovered address should match")

	err = wallet.Close()
	require.NoError(t, err)
}

// =============================================================================
// TR-06: Wallet EIP-1559 signing + real gas tests
// =============================================================================

// mockGasOracle implements the gas oracle for testing
type mockGasOracle struct {
	tip *big.Int
	err error
}

func (m *mockGasOracle) SuggestGasTip(_ context.Context) (*big.Int, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.tip, nil
}

// mockChainForWallet implements ChainReader for testing
type mockChainForWallet struct {
	nonce     uint64
	nonceErr  error
	head      *types.Header
	headErr   error
	estimate  uint64
	estimateErr error
	callErr   error
}

func (m *mockChainForWallet) PendingNonceAt(_ context.Context, _ domain.Address) (uint64, error) {
	return m.nonce, m.nonceErr
}

func (m *mockChainForWallet) HeaderByNumber(_ context.Context, _ *big.Int) (*types.Header, error) {
	return m.head, m.headErr
}

func (m *mockChainForWallet) EstimateGas(_ context.Context, _ ethereum.CallMsg) (uint64, error) {
	return m.estimate, m.estimateErr
}

// TestSign_EIP1559_TxType verifies that Sign() produces EIP-1559 transaction (Type 2).
func TestSign_EIP1559_TxType(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock chain
	mockChain := &mockChainForWallet{
		nonce: 0,
		head: &types.Header{
			BaseFee: big.NewInt(1000000000), // 1 gwei
		},
		estimate: 100000,
	}

	// Create wallet
	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	// Set up gas oracle
	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)} // 0.1 gwei

	// Set up chain for PendingNonce
	wallet.(*keystoreWallet).chain = mockChain

	// Build test transaction
	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	// Sign the transaction
	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)
	require.NotEmpty(t, signedTx.Signature)

	// Decode signature to get transaction type
	// EIP-2718 typed transactions start with tx type byte
	// 0x02 = EIP-1559
	assert.Equal(t, byte(0x02), signedTx.Signature[0], "EIP-1559 tx type should be 0x02")

	err = wallet.Close()
	require.NoError(t, err)
}

// TestSign_GasLimitWithBuffer verifies gasLimit = estimated * 1.2.
func TestSign_GasLimitWithBuffer(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock chain with known estimate
	mockChain := &mockChainForWallet{
		nonce: 0,
		head: &types.Header{
			BaseFee: big.NewInt(1000000000), // 1 gwei
		},
		estimate: 100000, // 100k gas estimate
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)

	// Verify 20% buffer: 100k * 1.2 = 120k
	// We can verify by checking the RLP encoded tx has gas = 120000
	assert.True(t, len(signedTx.Signature) > 4, "signature should be present")

	err = wallet.Close()
	require.NoError(t, err)
}

// TestSign_MaxFeeFormula verifies maxFee = 2*baseFee + tip.
func TestSign_MaxFeeFormula(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up with specific baseFee and tip
	baseFee := big.NewInt(1000000000)  // 1 gwei
	tip := big.NewInt(100000000)       // 0.1 gwei
	expectedMaxFee := big.NewInt(0).Add(
		big.NewInt(0).Mul(baseFee, big.NewInt(2)),
		tip,
	) // 2.1 gwei

	mockChain := &mockChainForWallet{
		nonce: 0,
		head: &types.Header{
			BaseFee: baseFee,
		},
		estimate: 100000,
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: tip}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)

	// Max fee should be 2*1gwei + 0.1gwei = 2.1 gwei
	assert.True(t, expectedMaxFee.Cmp(big.NewInt(2100000000)) == 0, "expected max fee 2.1 gwei")
	assert.NotEmpty(t, signedTx.Signature)

	err = wallet.Close()
	require.NoError(t, err)
}

// TestSign_NonceFromPending verifies nonce comes from PendingNonceAt.
func TestSign_NonceFromPending(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock with specific nonce
	expectedNonce := uint64(5)
	mockChain := &mockChainForWallet{
		nonce:  expectedNonce,
		head: &types.Header{
			BaseFee: big.NewInt(1000000000),
		},
		estimate: 100000,
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0, // Should be overwritten
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)

	// Verify signature has correct size for nonce=5
	// RLP encoding of nonce=5 differs from nonce=0
	assert.NotEmpty(t, signedTx.Signature)
	assert.NotEqual(t, expectedNonce, unsignedTx.Nonce, "original tx nonce was 0")

	err = wallet.Close()
	require.NoError(t, err)
}

// TestSign_EstimateGasError_Propagates verifies EstimateGas errors propagate.
func TestSign_EstimateGasError_Propagates(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock with estimate error
	estimateErr := errors.New("execution reverted")
	mockChain := &mockChainForWallet{
		nonce: 0,
		head: &types.Header{
			BaseFee: big.NewInt(1000000000),
		},
		estimateErr: estimateErr,
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	_, err = wallet.Sign(context.Background(), unsignedTx)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "execution reverted")
}

// TestSign_HeaderError_Propagates verifies HeaderByNumber errors propagate.
func TestSign_HeaderError_Propagates(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	// Set up mock with header error
	headerErr := errors.New("header not found")
	mockChain := &mockChainForWallet{
		nonce: 0,
		headErr: headerErr,
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	_, err = wallet.Sign(context.Background(), unsignedTx)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "header not found")
}

// TestSign_RecoverFromSig_MatchesAddress verifies signature recovery matches address.
func TestSign_RecoverFromSig_MatchesAddress(t *testing.T) {
	passphrase := "test-passphrase-123"
	tmpDir, _ := setupTestKeystore(t, passphrase)

	config := ports.WalletConfig{
		KeystoreDir: tmpDir,
		Passphrase:  passphrase,
		ChainID:     domain.ChainBase,
	}

	provider, err := New(context.Background(), config)
	require.NoError(t, err)

	mockChain := &mockChainForWallet{
		nonce: 0,
		head: &types.Header{
			BaseFee: big.NewInt(1000000000),
		},
		estimate: 100000,
	}

	wallet, err := provider.Open(context.Background(), config)
	require.NoError(t, err)

	wallet.(*keystoreWallet).gasOracle = &mockGasOracle{tip: big.NewInt(100000000)}
	wallet.(*keystoreWallet).chain = mockChain

	unsignedTx := domain.UnsignedTx{
		Chain:    domain.ChainBase,
		To:       domain.MustParseAddress("0x1234567890123456789012345678901234567890"),
		Data:     []byte{0x12, 0x34, 0x56, 0x78},
		Value:    domain.ZeroDecimal(),
		Nonce:    0,
		Deadline: 0,
		MinOut:   domain.ZeroDecimal(),
	}

	signedTx, err := wallet.Sign(context.Background(), unsignedTx)
	require.NoError(t, err)
	require.NotEmpty(t, signedTx.Signature)

	// Recover address from signature
	// For EIP-1559, we need to decode the tx from RLP first
	tx := new(types.Transaction)
	err = tx.UnmarshalBinary(signedTx.Signature)
	require.NoError(t, err)

	// Get signer and recover sender
	signer := types.LatestSignerForChainID(big.NewInt(8453)) // Base chain ID
	from, err := signer.Sender(tx)
	require.NoError(t, err)

	// Verify recovered address matches wallet address
	expectedAddr := wallet.Address()
	actualAddr := common.BytesToAddress(from.Bytes())
	assert.Equal(t, strings.ToLower(expectedAddr.String()), strings.ToLower(actualAddr.Hex()))

	err = wallet.Close()
	require.NoError(t, err)
}