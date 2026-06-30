"""Tests for display helpers: Title Case, provider labels, and icons."""

from src.display import source_icon, source_label, titlecase


def test_titlecase_basic_lowercase():
    assert titlecase("village underground") == "Village Underground"


def test_titlecase_preserves_styled_casing():
    # Already-styled names keep their casing.
    assert titlecase("Aphex Twin") == "Aphex Twin"
    assert titlecase("DJ EZ") == "DJ EZ"
    assert titlecase("SBTRKT") == "SBTRKT"


def test_titlecase_lowercases_connectors_in_middle():
    assert titlecase("nick cave and the bad seeds") == "Nick Cave and the Bad Seeds"


def test_titlecase_handles_numbers_in_venue():
    assert titlecase("o2 academy brixton") == "O2 Academy Brixton"


def test_titlecase_empty():
    assert titlecase("") == ""
    assert titlecase(None) == ""


def test_source_label_friendly_names():
    assert source_label("ra") == "Resident Advisor"
    assert source_label("ticketmaster") == "Ticketmaster"
    assert source_label("dice") == "Dice"


def test_source_icon_is_a_url_per_provider():
    assert "ra.co" in source_icon("ra")
    assert "ticketmaster.com" in source_icon("ticketmaster")
    assert source_icon("unknown") == ""
