package decimal

// Equal returns true if d equals other.
func (d Decimal) Equal(other Decimal) bool {
	return d.v.Equal(other.v)
}

// GreaterThan returns true if d is greater than other.
func (d Decimal) GreaterThan(other Decimal) bool {
	return d.v.GreaterThan(other.v)
}

// GreaterThanOrEqual returns true if d is greater than or equal to other.
func (d Decimal) GreaterThanOrEqual(other Decimal) bool {
	return d.v.GreaterThanOrEqual(other.v)
}

// LessThan returns true if d is less than other.
func (d Decimal) LessThan(other Decimal) bool {
	return d.v.LessThan(other.v)
}

// LessThanOrEqual returns true if d is less than or equal to other.
func (d Decimal) LessThanOrEqual(other Decimal) bool {
	return d.v.LessThanOrEqual(other.v)
}

// Cmp compares d and other and returns:
//   -1 if d < other
//    0 if d == other
//    1 if d > other
func (d Decimal) Cmp(other Decimal) int {
	cmp := d.v.Cmp(other.v)
	if cmp < 0 {
		return -1
	} else if cmp > 0 {
		return 1
	}
	return 0
}

// Min returns the smaller of a and b.
func Min(a, b Decimal) Decimal {
	if a.LessThan(b) {
		return a
	}
	return b
}

// Max returns the larger of a and b.
func Max(a, b Decimal) Decimal {
	if a.GreaterThan(b) {
		return a
	}
	return b
}