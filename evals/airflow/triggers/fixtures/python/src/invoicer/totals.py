from decimal import ROUND_HALF_UP, Decimal


def line_total(qty: int, unit_price: Decimal, discount_pct: Decimal = Decimal("0")) -> Decimal:
    gross = unit_price * qty
    return (gross * (1 - discount_pct / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def invoice_total(lines: list[dict], tax_pct: Decimal) -> Decimal:
    subtotal = sum(
        (line_total(ln["qty"], ln["unit_price"], ln.get("discount_pct", Decimal("0"))) for ln in lines),
        Decimal("0"),
    )
    return (subtotal * (1 + tax_pct / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
