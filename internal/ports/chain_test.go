package ports_test

// Compile-time assertions to ensure interface contracts are satisfied.
// Each test uses a nil pointer type assertion to verify that mock types
// implement their respective interfaces. If the mock does not implement
// the interface correctly, this file will fail to compile.
//
// Note: The actual mock implementations and assertions are defined in
// tests/property/mocks/chain_test.go to avoid import cycles.