from unittest.mock import patch

import requests

from localdirectory.plugins.osm_overpass import OSMOverpassPlugin, _ordered_endpoints


class StubResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"elements": []}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def plugin():
    return OSMOverpassPlugin(50.8739, 0.0088, 16.0934, timeout=1, user_agent="LocalDirectory-Test/1")


def test_endpoint_order_deduplicates_configured_primary():
    endpoints = _ordered_endpoints("https://overpass-api.de/api/interpreter")
    assert endpoints[0] == "https://overpass-api.de/api/interpreter"
    assert endpoints.count("https://overpass-api.de/api/interpreter") == 1
    assert "https://overpass.private.coffee/api/interpreter" in endpoints


@patch("localdirectory.plugins.osm_overpass.time.sleep", return_value=None)
@patch("localdirectory.plugins.osm_overpass.requests.post")
def test_overpass_fails_over_after_primary_5xx(mock_post, _sleep):
    mock_post.side_effect = [
        StubResponse(error=requests.HTTPError("504 Gateway Timeout")),
        StubResponse(error=requests.HTTPError("504 Gateway Timeout")),
        StubResponse(payload={"elements": []}),
    ]
    result = plugin().harvest()
    assert result.ok
    assert result.requests_made == 3
    assert "overpass.private.coffee" in result.message
    assert mock_post.call_args_list[-1].args[0] == "https://overpass.private.coffee/api/interpreter"


@patch("localdirectory.plugins.osm_overpass.time.sleep", return_value=None)
@patch("localdirectory.plugins.osm_overpass.requests.post")
def test_overpass_raises_only_after_all_endpoints_fail(mock_post, _sleep):
    mock_post.side_effect = [StubResponse(error=requests.Timeout("timeout")) for _ in range(4)]
    try:
        plugin().harvest()
    except RuntimeError as exc:
        assert "All Overpass endpoints failed" in str(exc)
        assert "overpass.private.coffee" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError after all Overpass endpoints fail")
