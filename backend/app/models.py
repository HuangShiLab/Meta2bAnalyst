"""
Meta2bAnalyst - Database Models (SQLAlchemy 2.0)
"""
import datetime
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def generate_uuid() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


class Session(Base):
    """Analysis session model."""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    name = Column(String(255), nullable=True)
    # Owning user; NULL marks shared/demo sessions visible to every
    # authenticated user (pre-auth deployments predate this column).
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    data_format = Column(String(50), nullable=True)  # feature_table, biom, mothur, 2brad
    analysis_level = Column(String(50), default="species")  # species, strain
    status = Column(String(50), default="created")  # created, uploading, processing, completed, error
    description = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    data_files = relationship("DataFile", back_populates="session", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="session", cascade="all, delete-orphan")


class DataFile(Base):
    """Uploaded data file model."""

    __tablename__ = "data_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    file_type = Column(String(50), nullable=False)  # feature_table, biom, shared, taxonomy, metadata, strain
    file_path = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    sample_count = Column(Integer, nullable=True)
    feature_count = Column(Integer, nullable=True)
    sample_names = Column(JSON, nullable=True)
    feature_names = Column(JSON, nullable=True)
    extra_metadata = Column(JSON, nullable=True)  # Additional file metadata
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    parsed_at = Column(DateTime, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="data_files")


class AnalysisJob(Base):
    """Analysis job model."""

    __tablename__ = "analysis_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(50), nullable=False)  # alpha, beta, differential, strain, pcoa, nmds, etc.
    parameters = Column(JSON, nullable=True)  # Job parameters
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    result_path = Column(String(500), nullable=True)  # Path to result file
    result_data = Column(JSON, nullable=True)  # Small result data stored inline
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    session = relationship("Session", back_populates="analysis_jobs")


class User(Base):
    """Application user for the lightweight multi-user deployment.

    Passwords are PBKDF2-HMAC-SHA256 hashes (stdlib, no extra dependency);
    sessions and uploads are scoped to the owning user.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="student", nullable=False)  # admin, student
    is_active = Column(Integer, default=1, nullable=False)  # 1/0, avoids a Boolean import for SQLite
    quota_mb = Column(Integer, nullable=True)  # NULL = server default (settings.USER_QUOTA_MB)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    sessions = relationship("Session", backref="owner")


class WorkflowTemplate(Base):
    """Named workflow template saved from the Workflow Builder.

    ``plan`` is the ExecutionPlan-shaped JSON (query/steps/...); ``layout``
    stores canvas coordinates so a loaded workflow looks the way it was saved.
    """

    __tablename__ = "workflow_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    plan = Column(JSON, nullable=False)
    layout = Column(JSON, nullable=True)  # [{"id": step_id, "x": int, "y": int}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
