package pancakeswap_v3_solana

import "testing"

func TestAdapterStub(t *testing.T) {
	a := &Adapter{}
	if a == nil {
		t.Fatal("adapter should not be nil")
	}
}
