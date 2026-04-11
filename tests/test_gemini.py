"""Unit tests for app/gemini.py — parse and classify functions."""

import os
from unittest.mock import patch, MagicMock

from app.gemini import FALLBACK, parse_gemini_response, classify_image


def test_parse_valid_gemini_response():
    text = '{"category":"pothole","severity":"high","department":"roads","description":"Large pothole"}'
    result = parse_gemini_response(text)
    assert result == {"category": "pothole", "severity": "high", "department": "roads", "description": "Large pothole"}


def test_parse_invalid_json_returns_fallback():
    assert parse_gemini_response("not json at all") == FALLBACK


def test_parse_missing_key_returns_fallback():
    text = '{"category":"pothole","severity":"high"}'
    assert parse_gemini_response(text) == FALLBACK


def test_parse_invalid_enum_returns_fallback():
    text = '{"category":"earthquake","severity":"high","department":"roads","description":"test"}'
    assert parse_gemini_response(text) == FALLBACK


def test_parse_empty_description_returns_fallback():
    text = '{"category":"pothole","severity":"high","department":"roads","description":""}'
    assert parse_gemini_response(text) == FALLBACK


def test_parse_gemini_markdown_wrapped_json():
    text = '```json\n{"category":"graffiti","severity":"low","department":"sanitation","description":"Wall tagged"}\n```'
    result = parse_gemini_response(text)
    assert result["category"] == "graffiti"
    assert result["description"] == "Wall tagged"


@patch("app.gemini.httpx.AsyncClient")
def test_groq_called_as_primary(mock_client_cls):
    import asyncio
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"category":"pothole","severity":"high","department":"roads","description":"test"}'}}]
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = MagicMock(return_value=mock_client)
    mock_client.__aexit__ = MagicMock(return_value=None)

    async def mock_post(*args, **kwargs):
        return mock_response
    mock_client.post = mock_post
    mock_client_cls.return_value = mock_client

    asyncio.get_event_loop().run_until_complete(classify_image(b"\xff\xd8\xff" + b"\x00" * 100))

    mock_client_cls.assert_called_once()
