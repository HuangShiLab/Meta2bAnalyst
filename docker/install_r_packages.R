#!/usr/bin/env Rscript
# Install the R packages Meta2bAnalyst can call.
#
# Run with Rscript at image build time -- not through rpy2. The previous
# installer (backend/scripts/install_r_packages.py) drove installation through
# rpy2 and wrote its report to a hardcoded absolute path on the author's laptop,
# so it could not run in a container at all. It also installed only
# DESeq2/edgeR/phyloseq, leaving ANCOMBC, ALDEx2, WGCNA, mixOmics and lefser
# missing -- which are exactly the methods the API refuses to approximate.
#
# Usage: Rscript install_r_packages.R [core|heavy|optional|all]  (default: all)
#
# Packages are split into groups so the Dockerfile can install them in separate
# layers: a failure in a later group does not invalidate the cached earlier
# ones (the core group alone is a ~15 minute compile).
#
# REQUIRED packages fail the build. OPTIONAL ones only warn: the application
# degrades honestly (those methods return HTTP 400 explaining what is missing)
# rather than silently substituting a different statistical method.

options(
  warn = 1,
  repos = c(CRAN = "https://cloud.r-project.org"),
  Ncpus = max(1L, parallel::detectCores())
)

# Packages whose absence makes the image not worth shipping. Each maps to a
# method the UI offers. Split by install cost / fragility:
CORE <- c(
  "vegan",      # community ecology helpers
  "DESeq2",     # differential abundance
  "edgeR",      # differential abundance
  "ALDEx2",     # compositional differential abundance
  "WGCNA",      # co-expression / co-occurrence modules
  "sva"         # ComBat / ComBat_seq batch correction (Phase 1)
)
# Heavy/fragile: ANCOMBC needs CVXR -> clarabel (Rust toolchain) and energy
# (GSL); mixOmics pulls rgl (headless GL). Kept in their own layer so a
# failure here does not rebuild CORE.
HEAVY <- c(
  "ANCOMBC",    # compositional differential abundance
  "mixOmics"    # DIABLO multi-block integration
)

# Nice to have; absence is reported by the API, not fatal to the build.
OPTIONAL <- c(
  "phyloseq",
  "lefser",     # LEfSe
  "maaslin3",   # note: lowercase is the Bioconductor package name
  "pheatmap",
  "ggplot2",
  "missForest", # missing-value imputation (random forest)
  "imputeLCMD", # QRILC imputation for LC-MS metabolomics
  "SpiecEasi"   # Phase 3 sparse inverse covariance / network (heavy compile)
)

args <- commandArgs(trailingOnly = TRUE)
group <- if (length(args)) args[[1]] else "all"
stopifnot(group %in% c("core", "heavy", "optional", "all"))

required <- switch(group,
  core = CORE,
  heavy = HEAVY,
  optional = character(0),
  all = c(CORE, HEAVY)
)
optional <- if (group %in% c("optional", "all")) OPTIONAL else character(0)

message("== Installing BiocManager ==")
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager")
}


namespace_error <- function(pkg) {
  # requireNamespace(quietly=TRUE) hides WHY a load fails; surface it so a
  # failed build log names the broken dependency instead of just 'MISSING'.
  tryCatch({
    loadNamespace(pkg)
    NULL
  }, error = function(e) conditionMessage(e))
}

install_one <- function(pkg) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    message(sprintf("  already present: %s", pkg))
    return(TRUE)
  }
  message(sprintf("  installing: %s", pkg))
  # BiocManager::install handles both CRAN and Bioconductor packages and, unlike
  # install.packages, resolves them against a consistent Bioconductor release.
  try(BiocManager::install(pkg, update = FALSE, ask = FALSE), silent = FALSE)
  if (requireNamespace(pkg, quietly = TRUE)) {
    return(TRUE)
  }
  err <- namespace_error(pkg)
  if (!is.null(err)) {
    message(sprintf("  !! %s installed but its namespace does not load: %s", pkg, err))
  }
  FALSE
}

message(sprintf("== Required packages (%s) ==", group))
required_status <- vapply(required, install_one, logical(1))

optional_status <- logical(0)
if (length(optional)) {
  message("== Optional packages ==")
  optional_status <- vapply(optional, install_one, logical(1))
}

report <- function(status) {
  for (pkg in names(status)) {
    message(sprintf("  %-12s %s", pkg, if (status[[pkg]]) "OK" else "MISSING"))
  }
}

message("")
message("========== R PACKAGE SUMMARY ==========")
message("required:")
report(required_status)
message("optional:")
report(optional_status)
message("=======================================")

missing_required <- names(required_status)[!required_status]
if (length(missing_required) > 0) {
  stop(sprintf(
    "Required R packages failed to install: %s\nThe image would advertise methods it cannot run.",
    paste(missing_required, collapse = ", ")
  ))
}

message("All required R packages installed.")
