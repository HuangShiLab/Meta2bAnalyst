"""Tests for API upload endpoints."""
import io
import tempfile
from pathlib import Path

import pandas as pd


class TestUploadAPI:
    """Test suite for file upload API endpoints."""

    def _create_tsv_upload(self, df, filename="test.tsv"):
        """Helper to create a multipart upload from a DataFrame as TSV."""
        tsv_buffer = io.BytesIO()
        df.to_csv(tsv_buffer, sep="\t", index=True)
        tsv_buffer.seek(0)
        return (filename, tsv_buffer, "text/tab-separated-values")

    def test_upload_csv_feature_table(self, client, mock_session_id, sample_feature_table):
        """Test uploading a TSV feature table (feature_table type uses TSV fallback)."""
        files = {"file": self._create_tsv_upload(sample_feature_table, "features.tsv")}
        response = client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "feature_table"},
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == mock_session_id
        assert data["file_type"] == "feature_table"
        assert data["status"] == "success"
        assert data["row_count"] == 20
        assert data["column_count"] == 10
        assert data["sample_count"] == 10
        assert data["feature_count"] == 20

    def test_upload_metadata(self, client, mock_session_id, sample_metadata):
        """Test uploading metadata TSV."""
        tsv_buffer = io.BytesIO()
        sample_metadata.to_csv(tsv_buffer, sep="\t", index=True)
        tsv_buffer.seek(0)
        files = {"file": ("metadata.tsv", tsv_buffer, "text/tab-separated-values")}
        response = client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "metadata"},
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file_type"] == "metadata"
        assert data["sample_count"] == 10

    def test_upload_strain_data(self, client, mock_session_id, sample_strain_data):
        """Test uploading strain-level TSV data."""
        tsv_buffer = io.BytesIO()
        sample_strain_data.to_csv(tsv_buffer, sep="\t", index=False)
        tsv_buffer.seek(0)
        files = {"file": ("strain_data.tsv", tsv_buffer, "text/tab-separated-values")}
        response = client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "strain"},
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file_type"] == "strain"

    def test_upload_invalid_session(self, client, sample_feature_table):
        """Test uploading to a non-existent session."""
        files = {"file": self._create_tsv_upload(sample_feature_table)}
        response = client.post(
            "/api/v1/sessions/nonexistent-id/upload",
            data={"file_type": "feature_table"},
            files=files,
        )
        assert response.status_code == 404

    def test_upload_no_file(self, client, mock_session_id):
        """Test uploading without a file."""
        response = client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "feature_table"},
        )
        assert response.status_code == 422

    def test_upload_invalid_extension(self, client, mock_session_id):
        """Test uploading with invalid file extension."""
        files = {"file": ("test.exe", io.BytesIO(b"invalid"), "application/octet-stream")}
        response = client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "feature_table"},
            files=files,
        )
        assert response.status_code == 400

    def test_list_files(self, client, mock_session_id, sample_feature_table):
        """Test listing uploaded files."""
        # Upload first
        files = {"file": self._create_tsv_upload(sample_feature_table, "features.tsv")}
        client.post(
            f"/api/v1/sessions/{mock_session_id}/upload",
            data={"file_type": "feature_table"},
            files=files,
        )
        response = client.get(f"/api/v1/sessions/{mock_session_id}/files")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) >= 1
