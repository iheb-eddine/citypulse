"""Tests for POST /api/reports — Step 3 (fallback values only)."""

import re
from io import BytesIO
from pathlib import Path

import pytest

from tests.conftest import JPEG_BYTES, PNG_BYTES


@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    """Mock AI API for all tests by default."""
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("mocked")
    monkeypatch.setattr("app.classifier.httpx.post", MagicMock(side_effect=Exception("mocked")))


@pytest.fixture(autouse=True)
def _use_tmp_uploads(tmp_path, monkeypatch):
    """Redirect file uploads to tmp_path for every test."""
    import app.main
    monkeypatch.setattr(app.main, "UPLOAD_DIR", tmp_path)


def _post(client, files=None, data=None):
    return client.post("/api/reports", files=files or {}, data=data or {})


def _valid_data():
    return {"latitude": "48.7758", "longitude": "9.1829"}


def _jpeg_file(name="test.jpg"):
    return {"photo": (name, BytesIO(JPEG_BYTES), "image/jpeg")}


# --- Success cases ---

def test_submit_valid_report(test_client, tmp_path):
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    body = r.json()
    assert body["category"] == "unclassified"
    assert body["severity"] == "medium"
    assert body["department"] == "general"
    assert body["description"] == "Classification pending \u2014 AI service unavailable"
    assert body["photo_path"].startswith("/static/uploads/")
    assert body["latitude"] == 48.7758
    assert body["longitude"] == 9.1829
    # File exists on disk
    fname = Path(body["photo_path"]).name
    assert (tmp_path / fname).exists()


def test_submit_valid_png(test_client):
    files = {"photo": ("test.png", BytesIO(PNG_BYTES), "image/png")}
    r = _post(test_client, files=files, data=_valid_data())
    assert r.status_code == 201
    assert r.json()["photo_path"].endswith(".png")


# --- File validation errors ---

def test_submit_missing_file(test_client):
    r = test_client.post("/api/reports", data=_valid_data())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MISSING_FILE"


def test_submit_empty_file(test_client):
    files = {"photo": ("empty.jpg", BytesIO(b""), "image/jpeg")}
    r = _post(test_client, files=files, data=_valid_data())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "EMPTY_FILE"


def test_submit_invalid_file_type(test_client):
    files = {"photo": ("test.txt", BytesIO(b"not an image"), "text/plain")}
    r = _post(test_client, files=files, data=_valid_data())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_FILE_TYPE"


def test_submit_file_too_large(test_client):
    files = {"photo": ("big.jpg", BytesIO(b"\x00" * 10_485_761), "image/jpeg")}
    r = _post(test_client, files=files, data=_valid_data())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"


# --- Coordinate validation errors ---

def test_submit_missing_latitude(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"longitude": "9.18"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LATITUDE"


def test_submit_missing_longitude(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"latitude": "48.77"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LONGITUDE"


def test_submit_latitude_out_of_range(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"latitude": "91.0", "longitude": "9.18"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LATITUDE"


def test_submit_longitude_out_of_range(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"latitude": "48.77", "longitude": "181.0"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LONGITUDE"


def test_submit_latitude_not_a_number(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"latitude": "abc", "longitude": "9.18"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LATITUDE"


# --- Boundary and security ---

def test_submit_negative_boundary_coordinates(test_client):
    r = _post(test_client, files=_jpeg_file(), data={"latitude": "-90.0", "longitude": "-180.0"})
    assert r.status_code == 201


def test_submit_file_renamed_to_uuid(test_client):
    files = {"photo": ("../../etc/passwd.jpg", BytesIO(JPEG_BYTES), "image/jpeg")}
    r = _post(test_client, files=files, data=_valid_data())
    assert r.status_code == 201
    path = r.json()["photo_path"]
    fname = Path(path).stem
    # UUID4 pattern
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", fname)
    assert ".." not in path


def test_submit_report_persisted_in_db(test_client, db_session):
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    from app.models import Report
    report = db_session.query(Report).filter_by(id=r.json()["id"]).first()
    assert report is not None
    assert report.latitude == 48.7758
    assert report.category == "unclassified"


# --- AI integration tests (Step 4) ---

def _mock_ai_response(monkeypatch, text=None, side_effect=None):
    """Patch app.classifier.httpx.post to return a mock with given response text or side_effect."""
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    if side_effect:
        monkeypatch.setattr("app.classifier.httpx.post", MagicMock(side_effect=side_effect))
    else:
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": text}]}}]
        }
        monkeypatch.setattr("app.classifier.httpx.post", MagicMock(return_value=mock_resp))


def test_submit_ai_fallback_on_timeout(test_client, monkeypatch, tmp_path):
    _mock_ai_response(monkeypatch, side_effect=TimeoutError("API timeout"))
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    assert r.json()["category"] == "unclassified"


def test_submit_ai_fallback_on_invalid_json(test_client, monkeypatch, tmp_path):
    _mock_ai_response(monkeypatch, text="I cannot analyze this image")
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    assert r.json()["category"] == "unclassified"


def test_submit_ai_fallback_on_invalid_category(test_client, monkeypatch, tmp_path):
    _mock_ai_response(
        monkeypatch,
        text='{"category":"earthquake","severity":"high","department":"roads","description":"Shaking"}',
    )
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    body = r.json()
    assert body["category"] == "unclassified"
    assert body["severity"] == "medium"
    assert body["department"] == "general"


def test_submit_ai_fallback_on_missing_field(test_client, monkeypatch, tmp_path):
    _mock_ai_response(
        monkeypatch,
        text='{"category":"pothole","severity":"high"}',
    )
    r = _post(test_client, files=_jpeg_file(), data=_valid_data())
    assert r.status_code == 201
    body = r.json()
    assert body["category"] == "unclassified"
    assert body["severity"] == "medium"
    assert body["department"] == "general"
