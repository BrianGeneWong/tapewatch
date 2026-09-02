from tapewatch.resolve import _normalize_name


def test_strips_corporate_suffixes():
    assert _normalize_name("Northwind Systems, Inc.") == "northwind systems"
    assert _normalize_name("Northwind Systems Corporation") == "northwind systems"
    assert _normalize_name("Northwind Systems Holdings LLC") == "northwind systems"


def test_normalizes_punctuation_and_case():
    assert _normalize_name("A.B.C. Industries") == "a b c industries"
    assert _normalize_name("  Contoso   Robotics  ") == "contoso robotics"


def test_distinct_companies_do_not_collide():
    """The normalizer must not be so aggressive that two different issuers
    map to the same key — a wrong ticker attaches an event to someone
    else's position, which is worse than not resolving it at all."""
    assert _normalize_name("Delta Air Lines Inc") != _normalize_name("Delta Apparel Inc")
