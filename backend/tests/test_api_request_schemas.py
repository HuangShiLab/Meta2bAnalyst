"""Request-schema contracts for endpoints that used to 422 on reasonable bodies.

Three endpoints rejected requests a caller could sensibly send:

* ``POST /sessions/{id}/export`` required ``export_type`` even though exporting
  the session's feature table is the only branch that needs nothing else.
* ``POST /agent/recommend`` required a hand-written ``data_summary`` and had no
  way to reference a session, although the recommender treats every key of that
  summary as optional and the server can read them off the uploads.
* ``POST /agent/write-paper`` was fine — the caller was sending ``section``
  instead of ``section_type``; that must keep failing, with the field named.
"""
import io

import pytest


@pytest.fixture
def session_with_data(client, mock_session_id, sample_feature_table, sample_metadata):
    """Upload a feature table and metadata to a session."""
    buf = io.BytesIO()
    sample_feature_table.to_csv(buf, sep="\t", index=True)
    buf.seek(0)
    client.post(
        f"/api/v1/sessions/{mock_session_id}/upload",
        data={"file_type": "feature_table"},
        files={"file": ("features.tsv", buf, "text/tab-separated-values")},
    )
    buf = io.BytesIO()
    sample_metadata.to_csv(buf, sep="\t", index=True)
    buf.seek(0)
    client.post(
        f"/api/v1/sessions/{mock_session_id}/upload",
        data={"file_type": "metadata"},
        files={"file": ("metadata.tsv", buf, "text/tab-separated-values")},
    )
    return mock_session_id


class TestExportRequestSchema:
    def test_format_only_exports_the_session_data(self, client, session_with_data):
        """{"format": "csv"} is a complete export request; export_type defaults to data."""
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/export",
            json={"format": "csv"},
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["export_type"] == "data"
        assert payload["format"] == "csv"
        assert payload["file_size"] > 0

    def test_explicit_export_type_still_honoured(self, client, session_with_data):
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/export",
            json={"export_type": "metadata", "format": "tsv"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["export_type"] == "metadata"

    def test_bad_export_type_names_the_field(self, client, session_with_data):
        response = client.post(
            f"/api/v1/sessions/{session_with_data}/export",
            json={"export_type": "nonsense", "format": "csv"},
        )
        assert response.status_code == 422, response.text
        assert "export_type" in response.json()["detail"]


class TestRecommendRequestSchema:
    def test_session_id_derives_the_data_summary(self, client, session_with_data):
        response = client.post(
            "/api/v1/agent/recommend",
            json={
                "session_id": session_with_data,
                "research_question": "which taxa differ between groups?",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        # 10 samples x 20 features come from the fixture upload.
        assert payload["sample_size"] == 10
        assert payload["data_type"] == "amplicon"
        assert payload["recommendations"]

    def test_explicit_data_summary_overrides_derived_values(self, client, session_with_data):
        response = client.post(
            "/api/v1/agent/recommend",
            json={
                "session_id": session_with_data,
                "data_summary": {"sample_size": 400, "study_design": "longitudinal"},
                "research_question": "does the community change over time?",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["sample_size"] == 400
        assert payload["study_design"] == "longitudinal"

    def test_data_summary_alone_still_works(self, client):
        response = client.post(
            "/api/v1/agent/recommend",
            json={
                "data_summary": {"data_type": "amplicon", "sample_size": 48, "n_groups": 2},
                "research_question": "find differential markers",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["sample_size"] == 48

    def test_no_data_source_names_both_fields(self, client):
        response = client.post(
            "/api/v1/agent/recommend",
            json={"research_question": "what should I run?"},
        )
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert "session_id" in detail and "data_summary" in detail

    def test_session_without_uploads_is_a_404_not_a_silent_guess(self, client, mock_session_id):
        response = client.post(
            "/api/v1/agent/recommend",
            json={"session_id": mock_session_id, "research_question": "what should I run?"},
        )
        assert response.status_code == 404, response.text
        assert "data_summary" in response.json()["detail"]


class TestWritePaperRequestSchema:
    def test_section_type_is_the_field_name(self, client):
        response = client.post(
            "/api/v1/agent/write-paper",
            json={"section_type": "methods", "results_summary": {"n_samples": 261}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["section_type"] == "methods"

    def test_wrong_field_name_is_rejected_and_named(self, client):
        """`section` is not the field; the 422 has to say which one is missing."""
        response = client.post(
            "/api/v1/agent/write-paper",
            json={"section": "methods", "results_summary": {"n_samples": 261}},
        )
        assert response.status_code == 422, response.text
        payload = response.json()
        assert "section_type" in payload["detail"]
        assert payload["fields"] == ["body.section_type"]
