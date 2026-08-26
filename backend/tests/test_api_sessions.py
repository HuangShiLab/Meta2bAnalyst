"""Tests for API sessions endpoints."""
import pytest

from app.schemas import SessionCreate


class TestSessionAPI:
    """Test suite for session management API endpoints."""

    def test_create_session(self, client):
        """Test creating a new session."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "name": "Test Session",
                "data_format": "csv",
                "analysis_level": "species",
                "description": "Test session created via pytest",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test Session"
        assert data["data_format"] == "csv"
        assert data["analysis_level"] == "species"
        assert data["status"] == "created"
        assert data["file_count"] == 0

    def test_create_session_minimal(self, client):
        """Test creating a session with minimal fields."""
        response = client.post(
            "/api/v1/sessions",
            json={
                "analysis_level": "strain",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["analysis_level"] == "strain"

    def test_list_sessions(self, client, mock_session_id):
        """Test listing sessions."""
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total" in data
        assert len(data["sessions"]) >= 1
        assert data["total"] >= 1

    def test_get_session(self, client, mock_session_id):
        """Test getting a specific session."""
        response = client.get(f"/api/v1/sessions/{mock_session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mock_session_id

    def test_get_session_not_found(self, client):
        """Test getting a non-existent session."""
        response = client.get("/api/v1/sessions/nonexistent-id")
        assert response.status_code == 404

    def test_update_session(self, client, mock_session_id):
        """Test updating a session."""
        response = client.put(
            f"/api/v1/sessions/{mock_session_id}",
            json={"name": "Updated Name", "status": "uploading"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["status"] == "uploading"

    def test_update_session_not_found(self, client):
        """Test updating a non-existent session."""
        response = client.put(
            "/api/v1/sessions/nonexistent-id",
            json={"name": "Updated"},
        )
        assert response.status_code == 404

    def test_delete_session(self, client):
        """Test deleting a session."""
        # Create a session to delete
        create_resp = client.post(
            "/api/v1/sessions",
            json={"name": "To Delete", "analysis_level": "species"},
        )
        session_id = create_resp.json()["id"]
        response = client.delete(f"/api/v1/sessions/{session_id}")
        assert response.status_code == 204

    def test_delete_session_not_found(self, client):
        """Test deleting a non-existent session."""
        response = client.delete("/api/v1/sessions/nonexistent-id")
        assert response.status_code == 404

    def test_demo_session_refuses_plain_delete(self, client):
        """Demo-flagged sessions (shared classroom dataset) need ?force=true."""
        create_resp = client.post(
            "/api/v1/sessions",
            json={"name": "Demo", "analysis_level": "species",
                  "metadata": {"demo": True}},
        )
        session_id = create_resp.json()["id"]

        refused = client.delete(f"/api/v1/sessions/{session_id}")
        assert refused.status_code == 409
        assert "force" in refused.json()["detail"]

        forced = client.delete(f"/api/v1/sessions/{session_id}?force=true")
        assert forced.status_code == 204

    def test_non_demo_session_delete_unaffected(self, client):
        """Sessions without the demo flag still delete without force."""
        create_resp = client.post(
            "/api/v1/sessions",
            json={"name": "Normal", "metadata": {"project": "x"}},
        )
        session_id = create_resp.json()["id"]
        assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
