"""
Smoke tests for web UI routes.

These tests verify that routes load without crashing.
They don't check for correctness, just that pages render with HTTP 200.
"""


def test_home_page_loads(client):
    """Test that the home page loads with an empty database."""
    response = client.get("/")
    assert response.status_code == 200
    # Verify it's actually HTML content
    assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data


def test_wrap_latest_page_loads_without_data(client):
    response = client.get("/calendar/wrap")
    assert response.status_code == 200
    assert b"Year Wrap" in response.data


def test_wrap_year_page_loads_without_data(client):
    response = client.get("/calendar/wrap/2026")
    assert response.status_code == 200
    assert b"Year Wrap" in response.data


def test_wrap_month_page_loads_without_data(client):
    response = client.get("/calendar/wrap/2026/1")
    assert response.status_code == 200
    assert b"Month Wrap" in response.data
