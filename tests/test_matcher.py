"""Tests for artist-name normalization.

The fuzzy-matching tests join these in milestone 3; normalization is the piece
that already exists and is most likely to silently regress.
"""

from src.matcher import normalize_name


def test_lowercases():
    assert normalize_name("Aphex Twin") == "aphex twin"


def test_strips_diacritics():
    assert normalize_name("Björk") == "bjork"
    assert normalize_name("Sigur Rós") == "sigur ros"


def test_removes_leading_the():
    assert normalize_name("The Prodigy") == "prodigy"
    # "the" only stripped when leading.
    assert normalize_name("Sunburst The Band") == "sunburst the band"


def test_strips_punctuation_and_collapses_whitespace():
    assert normalize_name("Godspeed You! Black Emperor") == "godspeed you black emperor"
    assert normalize_name("  Boards   of  Canada ") == "boards of canada"


def test_combined():
    assert normalize_name("The Chemical Brothers!") == "chemical brothers"
