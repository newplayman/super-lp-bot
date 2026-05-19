package domain

import (
	"crypto/ed25519"
	"errors"
	"fmt"
	"strings"

	"github.com/btcsuite/btcd/btcutil/base58"
)

var (
	ErrInvalidEVMAddress    = errors.New("invalid EVM address")
	ErrInvalidSolanaAddress = errors.New("invalid Solana address")
)

type Address struct {
	chain ChainID
	data  []byte // 20 bytes for EVM, 32 bytes for Solana
}

func MustParseAddress(s string) Address {
	a, err := ParseAddress(s)
	if err != nil {
		panic(err)
	}
	return a
}

func ParseAddress(s string) (Address, error) {
	if strings.HasPrefix(s, "0x") || strings.HasPrefix(s, "0X") {
		return parseEVMAddress(s)
	}
	return parseSolanaAddress(s)
}

func parseEVMAddress(s string) (Address, error) {
	if len(s) != 42 {
		return Address{}, fmt.Errorf("%w: expected 42 chars, got %d", ErrInvalidEVMAddress, len(s))
	}
	data, err := hexDecode(s[2:])
	if err != nil {
		return Address{}, fmt.Errorf("%w: %v", ErrInvalidEVMAddress, err)
	}
	if len(data) != 20 {
		return Address{}, fmt.Errorf("%w: expected 20 bytes, got %d", ErrInvalidEVMAddress, len(data))
	}
	return Address{chain: ChainBase, data: data}, nil // EVM address implies base chain
}

func parseSolanaAddress(s string) (Address, error) {
	data := base58.Decode(s)
	if len(data) != ed25519.PublicKeySize { // 32 bytes
		return Address{}, fmt.Errorf("%w: expected 32 bytes, got %d", ErrInvalidSolanaAddress, len(data))
	}
	return Address{chain: ChainSolana, data: data}, nil
}

func (a Address) String() string {
	if a.chain == ChainSolana {
		return base58.Encode(a.data)
	}
	return "0x" + hexEncode(a.data)
}

func (a Address) Chain() ChainID { return a.chain }
func (a Address) Bytes() []byte  { return a.data }

func (a Address) IsZero() bool {
	for _, b := range a.data {
		if b != 0 {
			return false
		}
	}
	return true
}

// hexEncode encodes bytes to hex string (uppercase)
func hexEncode(data []byte) string {
	const hexChars = "0123456789ABCDEF"
	result := make([]byte, len(data)*2)
	for i, b := range data {
		result[i*2] = hexChars[b>>4]
		result[i*2+1] = hexChars[b&0x0f]
	}
	return string(result)
}

// hexDecode decodes hex string to bytes
func hexDecode(s string) ([]byte, error) {
	if len(s)%2 != 0 {
		return nil, errors.New("hex string must have even length")
	}
	result := make([]byte, len(s)/2)
	for i := 0; i < len(s); i += 2 {
		hi := hexValue(s[i])
		lo := hexValue(s[i+1])
		if hi < 0 || lo < 0 {
			return nil, errors.New("invalid hex character")
		}
		result[i/2] = byte(hi<<4 | lo)
	}
	return result, nil
}

// hexValue returns the numeric value of a hex character, or -1 if invalid
func hexValue(c byte) int {
	switch {
	case c >= '0' && c <= '9':
		return int(c - '0')
	case c >= 'A' && c <= 'F':
		return int(c - 'A' + 10)
	case c >= 'a' && c <= 'f':
		return int(c - 'a' + 10)
	default:
		return -1
	}
}