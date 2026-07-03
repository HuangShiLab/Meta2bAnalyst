"""Tests for API strain endpoints."""
import io

import pytest


class TestStrainAPI:
    """Test suite for strain-level analysis API endpoints."""

    @pytest.fixture
    def session_with_strain_data(self, client, mock_session_id, sample_strain_data):
        """Upload strain data and metadata to a session."""
        tsv_buffer = io.BytesIO()
        sample_strain_data.to_csv(tsv_buffer, sep="\t", index=False)
        tsv_buffer.seek(0)
        files = {"file": ("strain_data.tsv", tsv_buffer, "text/tab-separated-values")}
        client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "strain"},
            files=files,
        )
        return mock_session_id

    @pytest.fixture
    def session_with_strain_and_metadata(self, client, session_with_strain_data, sample_metadata):
        """Upload metadata to a session that already has strain data."""
        tsv_buffer = io.BytesIO()
        sample_metadata.to_csv(tsv_buffer, sep="\t", index=True)
        tsv_buffer.seek(0)
        files = {"file": ("metadata.tsv", tsv_buffer, "text/tab-separated-values")}
        client.post(
            f"/api/v1/sessions/{session_with_strain_data}/upload",
            data={"file_type": "metadata"},
            files=files,
        )
        return session_with_strain_data

    def test_strain_composition(self, client, session_with_strain_data):
        """Test strain composition endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_data}/analyze/strain/composition",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == session_with_strain_data
        assert data["species"] == "Escherichia_coli"
        assert data["analysis_type"] == "strain_composition"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_strain_alpha(self, client, session_with_strain_data):
        """Test strain alpha diversity endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_data}/analyze/strain/alpha",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {"metric": "shannon"},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["analysis_type"] == "strain_alpha"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_strain_beta(self, client, session_with_strain_data):
        """Test strain beta diversity endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_data}/analyze/strain/beta",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {"distance": "braycurtis"},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["analysis_type"] == "strain_beta"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_strain_differential(self, client, session_with_strain_and_metadata):
        """Test strain differential endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_and_metadata}/analyze/strain/differential",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {"group_var": "Treatment"},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["analysis_type"] == "strain_differential"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_strain_dominance(self, client, session_with_strain_data):
        """Test strain dominance endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_data}/analyze/strain/dominance",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["analysis_type"] in ("strain_dominance", "strain_composition")
        assert data["status"] == "completed"

    def test_strain_replacement(self, client, session_with_strain_and_metadata):
        """Test strain replacement endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_and_metadata}/analyze/strain/replacement",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
                "parameters": {"group_var": "Treatment", "group1": "Control", "group2": "Treatment"},
                "min_ani": 95.0,
                "min_coverage": 0.8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "completed"

    def test_strain_invalid_session(self, client):
        """Test strain endpoint with invalid session."""
        response = client.post(
            "/api/v1/sessions/nonexistent-id/analyze/strain/composition",
            json={
                "species": "Escherichia_coli",
                "analysis_type": "strain_profile",
            },
        )
        assert response.status_code == 404

    def test_strain_invalid_request(self, client, session_with_strain_data):
        """Test strain endpoint with invalid request (missing species)."""
        response = client.post(
            f"/api/v1/sessions/{session_with_strain_data}/analyze/strain/composition",
            json={
                "analysis_type": "strain_profile",
                "parameters": {},
            },
        )
        # Missing species is a 422 validation error from the StrainAnalysisRequest schema
        assert response.status_code in (422, 500)
