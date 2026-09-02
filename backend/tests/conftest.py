"""pytest fixtures for Meta2bAnalyst backend tests."""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# The auth middleware must not gate the API during tests: the suite predates
# per-user auth and calls endpoints without tokens. Set before app import so
# pydantic-settings picks it up.
os.environ.setdefault("AUTH_REQUIRED", "false")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


# ─────────────────────────────── Database fixtures


@pytest.fixture(autouse=True, scope="session")
def _disable_llm_for_tests():
    """Hermetic tests: the real Kimi gateway must never be called from pytest.

    With LLM planner fallback now enabled by default, a clarification query in
    a dev shell (where backend/.env carries a real KIMI_API_KEY) would
    otherwise hit the network and make tests flaky and slow. Force the shared
    client into its unavailable state; tests that exercise the LLM path mock
    it explicitly.
    """
    from app.services import llm_client as lc

    client = lc.get_llm_client()
    client.api_key = None
    client._available = False
    yield



@pytest.fixture(scope="session")
def test_engine():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    os.unlink(db_path)


@pytest.fixture(scope="function")
def db_session(test_engine):
    """Create a new database session for each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ─────────────────────────────── Sample data fixtures


@pytest.fixture
def sample_feature_table():
    """Return a 10 samples x 20 features abundance DataFrame."""
    np.random.seed(42)
    samples = [f"Sample_{i:02d}" for i in range(1, 11)]
    features = [f"Feature_{i:02d}" for i in range(1, 21)]
    data = np.random.poisson(lam=50, size=(20, 10)).astype(float)
    # Ensure no all-zero rows/columns
    data[0, :] = 0
    data[:, 0] = 0
    data[0, 0] = 10
    df = pd.DataFrame(data, index=features, columns=samples)
    return df


@pytest.fixture
def sample_metadata():
    """Return metadata for 10 samples with a grouping variable."""
    samples = [f"Sample_{i:02d}" for i in range(1, 11)]
    groups = ["Control"] * 5 + ["Treatment"] * 5
    metadata = pd.DataFrame({
        "Treatment": groups,
        "Age": np.random.randint(20, 60, size=10),
        "Sex": np.random.choice(["M", "F"], size=10),
    }, index=samples)
    return metadata


@pytest.fixture
def sample_metadata_no_numeric_groups():
    """Return metadata without numeric columns that could be mistaken for grouping variables."""
    samples = [f"Sample_{i:02d}" for i in range(1, 11)]
    groups = ["Control"] * 5 + ["Treatment"] * 5
    metadata = pd.DataFrame({
        "Treatment": groups,
    }, index=samples)
    return metadata


@pytest.fixture
def sample_strain_data():
    """Return sample strain-level data (long format)."""
    np.random.seed(42)
    records = []
    samples = [f"Sample_{i:02d}" for i in range(1, 11)]
    species_list = ["Escherichia_coli", "Staphylococcus_aureus"]
    for sample in samples:
        for species in species_list:
            n_strains = np.random.randint(2, 5)
            for j in range(n_strains):
                records.append({
                    "sample_id": sample,
                    "species": species,
                    "strain": f"{species}_strain_{j+1}",
                    "abundance": float(np.random.poisson(20)),
                    "ani": float(np.random.uniform(95.0, 100.0)),
                    "coverage": float(np.random.uniform(0.8, 1.0)),
                })
    df = pd.DataFrame(records)
    return df


@pytest.fixture
def mock_session_id(client):
    """Create a mock session and return session_id."""
    response = client.post(
        "/api/v1/sessions",
        json={
            "name": "Test Session",
            "data_format": "csv",
            "analysis_level": "species",
            "description": "Test session for pytest",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


# ─────────────────────────────── Temporary file helpers


@pytest.fixture
def temp_csv_file(sample_feature_table):
    """Create a temporary CSV file from the sample feature table."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        path = f.name
    sample_feature_table.to_csv(path)
    yield path
    os.unlink(path)


@pytest.fixture
def temp_tsv_file(sample_feature_table):
    """Create a temporary TSV file from the sample feature table."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        path = f.name
    sample_feature_table.to_csv(path, sep="\t")
    yield path
    os.unlink(path)


@pytest.fixture
def temp_metadata_file(sample_metadata):
    """Create a temporary metadata TSV file."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        path = f.name
    sample_metadata.to_csv(path, sep="\t")
    yield path
    os.unlink(path)


@pytest.fixture
def temp_strain_file(sample_strain_data):
    """Create a temporary strain data TSV file."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        path = f.name
    sample_strain_data.to_csv(path, sep="\t", index=False)
    yield path
    os.unlink(path)


@pytest.fixture
def temp_biom_file():
    """Create a temporary BIOM JSON file."""
    biom_data = {
        "id": "test",
        "format": "Biological Observation Matrix 1.0.0",
        "format_url": "http://biom-format.org",
        "matrix_type": "dense",
        "generated_by": "pytest",
        "date": "2024-01-01T00:00:00",
        "type": "OTU table",
        "matrix_element_type": "int",
        "shape": [5, 5],
        "data": [
            [10, 20, 30, 40, 50],
            [5, 15, 25, 35, 45],
            [8, 12, 18, 22, 28],
            [3, 7, 11, 15, 19],
            [1, 2, 3, 4, 5],
        ],
        "rows": [
            {"id": "OTU_1", "metadata": {"taxonomy": "k__Bacteria;p__Firmicutes"}},
            {"id": "OTU_2", "metadata": {"taxonomy": "k__Bacteria;p__Proteobacteria"}},
            {"id": "OTU_3", "metadata": {"taxonomy": "k__Bacteria;p__Actinobacteria"}},
            {"id": "OTU_4", "metadata": {"taxonomy": "k__Bacteria;p__Bacteroidetes"}},
            {"id": "OTU_5", "metadata": {"taxonomy": "k__Bacteria;p__Tenericutes"}},
        ],
        "columns": [
            {"id": "Sample_01", "metadata": {"group": "Control"}},
            {"id": "Sample_02", "metadata": {"group": "Control"}},
            {"id": "Sample_03", "metadata": {"group": "Control"}},
            {"id": "Sample_04", "metadata": {"group": "Treatment"}},
            {"id": "Sample_05", "metadata": {"group": "Treatment"}},
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".biom", delete=False, mode="w") as f:
        path = f.name
        json.dump(biom_data, f)
    yield path
    os.unlink(path)


@pytest.fixture
def temp_mothur_shared_file():
    """Create a temporary Mothur shared file."""
    lines = [
        "label\tgroup\tnumOtus\tOTU_1\tOTU_2\tOTU_3\tOTU_4\tOTU_5",
        "0.03\tSample_01\t5\t10\t20\t30\t40\t50",
        "0.03\tSample_02\t5\t5\t15\t25\t35\t45",
        "0.03\tSample_03\t5\t8\t12\t18\t22\t28",
        "0.03\tSample_04\t5\t3\t7\t11\t15\t19",
        "0.03\tSample_05\t5\t1\t2\t3\t4\t5",
    ]
    with tempfile.NamedTemporaryFile(suffix=".shared", delete=False, mode="w") as f:
        path = f.name
        f.write("\n".join(lines))
    yield path
    os.unlink(path)


@pytest.fixture
def temp_mothur_taxonomy_file():
    """Create a temporary Mothur taxonomy file."""
    lines = [
        "OTU_1\tk__Bacteria(100);p__Firmicutes(95);\t5",
        "OTU_2\tk__Bacteria(100);p__Proteobacteria(90);\t5",
        "OTU_3\tk__Bacteria(100);p__Actinobacteria(85);\t5",
        "OTU_4\tk__Bacteria(100);p__Bacteroidetes(88);\t5",
        "OTU_5\tk__Bacteria(100);p__Tenericutes(80);\t5",
    ]
    with tempfile.NamedTemporaryFile(suffix=".taxonomy", delete=False, mode="w") as f:
        path = f.name
        f.write("\n".join(lines))
    yield path
    os.unlink(path)


@pytest.fixture
def temp_strain2bscan_file(sample_strain_data):
    """Create a temporary Strain2bScan TSV file."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        path = f.name
    sample_strain_data.to_csv(path, sep="\t", index=False)
    yield path
    os.unlink(path)
