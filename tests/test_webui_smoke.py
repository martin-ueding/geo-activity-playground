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

