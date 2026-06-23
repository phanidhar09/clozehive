"""parse_price_to_float — scraped OG/JSON-LD price strings → float for cost-per-wear."""

import pytest

from app.api.v1.intelligence.services.shopping_check_service import parse_price_to_float


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$129.99", 129.99),
        ("129.99", 129.99),
        ("USD 1,299.00", 1299.00),  # US thousands separator
        ("1.299,00 €", 1299.00),  # EU thousands separator
        ("129,99", 129.99),  # EU decimal comma
        ("1299", 1299.00),
        ("  $ 89 ", 89.00),
        (49.5, 49.5),  # already numeric
        (200, 200.0),
    ],
)
def test_parses_valid_prices(raw, expected):
    assert parse_price_to_float(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "Sold out", "free", "0", "$0.00", -5, "N/A"])
def test_rejects_unparseable_or_nonpositive(raw):
    assert parse_price_to_float(raw) is None
