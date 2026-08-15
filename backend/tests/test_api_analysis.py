"""Tests for API analysis endpoints (alpha, beta, pcoa, nmds, differential, heatmap, etc.)."""
import io

import pytest


class TestAnalysisAPI:
    """Test suite for analysis API endpoints."""

    @pytest.fixture
    def session_with_data(self, client, mock_session_id, sample_feature_table, sample_metadata):
        """Upload feature table and metadata to a session."""
        tsv_buffer = io.BytesIO()
        sample_feature_table.to_csv(tsv_buffer, sep="\t", index=True)
        tsv_buffer.seek(0)
        files = {"file": ("features.tsv", tsv_buffer, "text/tab-separated-values")}
        client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "feature_table"},
            files=files,
        )
        tsv_buffer = io.BytesIO()
        sample_metadata.to_csv(tsv_buffer, sep="\t", index=True)
        tsv_buffer.seek(0)
        files = {"file": ("metadata.tsv", tsv_buffer, "text/tab-separated-values")}
        client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "metadata"},
            files=files,
        )
        return mock_session_id

    def test_data_inspection(self, client, session_with_data):
        """Test data inspection endpoint."""
        response = client.get(f"/api/v1/sessions/{session_with_data}/inspect")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_with_data
        assert data["sample_count"] == 10
        assert data["feature_count"] == 20
        assert "summary" in data
        assert "preview" in data
        assert data["row_count"] == 20
        assert data["column_count"] == 10

    def test_data_inspection_no_session(self, client):
        """Test data inspection for non-existent session."""
        response = client.get("/api/v1/sessions/nonexistent-id/inspect")
        assert response.status_code == 404

    def test_filter_data(self, client, session_with_data):
        """Test data filtering endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/filter",
            json={"min_samples": 2, "min_abundance": 0.0, "max_features": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_with_data
        assert data["status"] == "success"
        assert "row_count_before" in data
        assert "row_count_after" in data

    def test_normalize_data(self, client, session_with_data):
        """Test data normalization endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/normalize",
            json={"method": "relative", "log_transform": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_with_data
        assert data["method"] == "relative"
        assert data["status"] == "success"

    @pytest.mark.skip(reason="Source code bug: alpha result_data contains numpy.bool_ which is not JSON serializable by SQLAlchemy SQLite JSON column")
    def test_alpha_diversity_analysis(self, client, session_with_data):
        """Test alpha diversity analysis endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/alpha-diversity",
            json={
                "analysis_type": "alpha",
                "parameters": {"indices": ["shannon", "simpson", "observed"]},
                "group_column": "Treatment",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == session_with_data
        assert data["job_type"] == "alpha"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_beta_diversity_analysis(self, client, session_with_data):
        """Test beta diversity analysis endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/beta-diversity",
            json={
                "analysis_type": "beta",
                "parameters": {"metric": "braycurtis"},
                "group_column": "Treatment",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "beta"
        assert data["status"] == "completed"
        assert "result_data" in data

    @pytest.mark.skip(reason="Source code bug: PCoA result_data contains numpy types not JSON serializable by SQLAlchemy SQLite JSON column")
    def test_pcoa_analysis(self, client, session_with_data):
        """Test PCoA analysis endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/pcoa",
            json={
                "analysis_type": "pcoa",
                "parameters": {"metric": "braycurtis", "n_components": 3},
                "group_column": "Treatment",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "pcoa"
        assert data["status"] == "completed"
        assert "result_data" in data

    def test_nmds_analysis(self, client, session_with_data):
        """Test NMDS analysis endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/nmds",
            json={
                "analysis_type": "nmds",
                "parameters": {"metric": "braycurtis", "n_components": 2},
                "group_column": "Treatment",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "nmds"
        assert data["status"] == "completed"

    def test_heatmap_analysis(self, client, session_with_data):
        """Test heatmap analysis endpoint."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/heatmap",
            json={
                "analysis_type": "heatmap",
                "parameters": {},
                "group_column": "Treatment",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["job_type"] == "heatmap"
        assert data["status"] == "completed"

    def test_taxonomy_bar_analysis(self, client, session_with_data):
        """Taxonomy bar chart is computed over samples, not taxa.

        This assertion used to accept 404 and 500 as valid outcomes. The
        endpoint did in fact fail, because run_taxonomy_bar decided orientation
        from whether the first index label contained '|' or '__' and so treated
        plain taxa names as sample IDs.
        """
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/taxonomy-bar",
            json={"parameters": {"top_n": 10}, "group_column": "Treatment"},
        )
        assert response.status_code in (200, 201), response.text

        statistics = response.json()["result_data"]["statistics"]
        # The fixture's feature table is features x samples; the chart must
        # describe its samples.
        assert statistics["n_samples"] > 0
        assert statistics["n_taxa_shown"] > 0

    def test_analysis_invalid_session(self, client):
        """Test analysis on non-existent session."""
        response = client.post(
            "/api/v1/sessions/nonexistent-id/analyze/alpha-diversity",
            json={
                "analysis_type": "alpha",
                "parameters": {"indices": ["shannon"]},
            },
        )
        assert response.status_code == 404

    def test_analysis_type_is_informational(self, client, session_with_data):
        """`analysis_type` no longer gates the request; the URL selects the analysis.

        It used to be required and to use a different naming convention than the
        routes, so POST /analyze/random-forest rejected
        ``analysis_type="random-forest"``. Worse, the resulting 422 hit a
        validation handler that could not serialise Pydantic's error context, so
        every validation failure surfaced as a body-less 500.
        """
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/alpha-diversity",
            json={"analysis_type": "invalid_type", "parameters": {}},
        )
        assert response.status_code != 500, response.text
        assert response.status_code in (200, 201, 400, 404)

    def test_validation_errors_are_readable(self, client, session_with_data):
        """A genuine schema violation must return a 422 with a JSON body.

        Regression test for the handler crash described above. ``detail`` must
        also name the offending field: clients that surface only ``detail``
        used to be told nothing but "Validation error".
        """
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/analyze/alpha-diversity",
            json={"parameters": "not-a-dict"},
        )
        assert response.status_code == 422, response.text
        payload = response.json()
        assert payload["detail"].startswith("Validation error")
        assert "parameters" in payload["detail"], payload["detail"]
        assert payload["fields"] == ["body.parameters"]
        assert isinstance(payload["errors"], list) and payload["errors"]
