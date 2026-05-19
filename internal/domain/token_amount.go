package domain

import (
	"fmt"
	"strings"
)

// Token represents a token (ERC20 / SPL).
type Token struct {
	Address  Address
	Symbol   string
	Decimals uint8
	Chain    ChainID
}

// TokenAmount is an amount of a specific token.
type TokenAmount struct {
	Token  Token
	Amount Decimal
}

func (ta TokenAmount) InUSD(price Decimal) Decimal {
	// Convert raw amount to display amount (dividing by decimals) before multiplying by price
	divisor := MustDecimal("1" + strings.Repeat("0", int(ta.Token.Decimals)))
	displayAmount := ta.Amount.Div(divisor)
	return displayAmount.Mul(price)
}

func (ta TokenAmount) String() string {
	return fmt.Sprintf("%s %s", ta.Amount.String(), ta.Token.Symbol)
}

// Display returns a human readable amount (adjusted by decimals).
func (ta TokenAmount) Display() string {
	divisor := MustDecimal("1" + strings.Repeat("0", int(ta.Token.Decimals)))
	displayAmount := ta.Amount.Div(divisor)
	return displayAmount.String()
}