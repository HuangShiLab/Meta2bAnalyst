# Meta2bAnalyst backend, with R so the R-backed methods actually run.
#
# Base image choice: bioconductor_docker ships R plus the long tail of system
# libraries (libxml2, libcurl, gsl, glpk, ...) that DESeq2 / ANCOMBC / mixOmics /
# WGCNA need in order to compile. Starting from python:slim and apt-installing
# r-base means discovering those dependencies one failed compile at a time.
#
# The build is slow (R packages compile from source; budget 30-60 min on first
# build) and the image is large (~4-5 GB). That is the cost of the R methods
# being real rather than silently approximated -- see app/services/r_analysis.py.
FROM bioconductor/bioconductor_docker:RELEASE_3_20

WORKDIR /app

# curl is used by the HEALTHCHECK below; do not assume the base image has it.
# libgsl-dev: the R package 'energy' (ANCOMBC dep) links against GSL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgsl-dev \
    && rm -rf /var/lib/apt/lists/*

# Rust toolchain: clarabel (CVXR -> ANCOMBC dep) compiles a Rust library and
# the distro rustc is too old for its crates. rustup minimal profile.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --profile minimal \
    && /root/.cargo/bin/rustc --version
ENV PATH="/root/.cargo/bin:$PATH"

# ── R packages ───────────────────────────────────────────────────────────────
# Done before the Python layer so that editing application code does not
# invalidate the (expensive) R layer. Split into three layers by install
# cost/fragility so a heavy-group failure does not rebuild the core group.
COPY docker/install_r_packages.R /tmp/install_r_packages.R
RUN Rscript /tmp/install_r_packages.R core
# Version pins (gsl, CVXR) in their own layer: editing the pin list must not
# invalidate the core layer. See pin_r_packages.R for why each pin exists.
COPY docker/pin_r_packages.R /tmp/pin_r_packages.R
RUN Rscript /tmp/pin_r_packages.R && rm /tmp/pin_r_packages.R
RUN Rscript /tmp/install_r_packages.R heavy
RUN Rscript /tmp/install_r_packages.R optional && rm /tmp/install_r_packages.R

# ── Python ───────────────────────────────────────────────────────────────────
# The base image's python3 is externally managed (PEP 668), so use a venv rather
# than --break-system-packages.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# rpy2 is optional in requirements.txt (it needs a working R, which only this
# image has). Installing it here is what turns "R::DESeq2" on.
RUN pip install --no-cache-dir "rpy2==3.5.15"

# ── Application ──────────────────────────────────────────────────────────────
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/
COPY backend/examples/ ./examples/

# Worked-example datasets (Huang mBio 2021: 261 samples x 44 genera + 1125
# metabolites + metadata). Bundled so a tester can exercise the whole pipeline,
# and so `python scripts/pipeline_smoke.py` runs inside the container.
COPY Huang_mBio_microbiome.tsv Huang_mBio_metabolome.tsv Huang_mBio_metadata.tsv ./examples/

# `data` holds the SQLite file. SQLAlchemy will not create a missing parent
# directory, so a bind/volume mount target must exist before first start.
RUN mkdir -p uploads logs data

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UPLOAD_DIR=/app/uploads \
    LOG_DIR=/app/logs

# Fail the build if the wiring is broken, rather than shipping an image that
# starts and then 500s on the first request.
RUN python -c "import app.main; print('app imports OK')" \
    && python -c "from app.services.r_analysis import rpy2_available, rpackage_available; \
assert rpy2_available(), 'rpy2 not usable'; \
missing=[p for p in ('DESeq2','edgeR','ANCOMBC','ALDEx2','mixOmics','WGCNA','sva') if not rpackage_available(p)]; \
assert not missing, f'R packages unusable from Python: {missing}'; \
print('R integration OK')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
