"""Tests for Spotify client helpers that don't hit the network."""

import httpx

from src.models import Artist
from src.spotify_client import enrich_images


class _RaisingClient:
    """Stand-in httpx client whose GET always fails, like a 403 catalog endpoint."""

    def get(self, *args, **kwargs):
        request = httpx.Request("GET", "https://api.spotify.com/v1/artists")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("403", request=request, response=response)


def test_enrich_images_is_best_effort():
    artists = [Artist("id1", "Bonobo", "bonobo", "liked", image_url=None)]
    # Must not raise even though the underlying call 403s.
    enrich_images(_RaisingClient(), artists)
    assert artists[0].image_url is None  # left as-is, no crash
