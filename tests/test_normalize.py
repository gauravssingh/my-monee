from mymonee.merchants.normalize import normalize_merchant


def test_normalize_strips_gateway_prefix() -> None:
    assert normalize_merchant("RAZ*SWIGGY BANGALORE") == "Swiggy Bangalore"
