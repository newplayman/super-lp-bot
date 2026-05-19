package aerodrome

import "testing"

func TestAdapterStub(t *testing.T) {
	// Verify the adapter type exists and can be instantiated
	a := &Adapter{}
	if a == nil {
		t.Fatal("adapter should not be nil")
	}
}