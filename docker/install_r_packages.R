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
# REQUIRED packages fail the build. OPTIONAL ones only warn: the application
# degrades honestly (those methods return HTTP 400 explaining what is missing)
# rather than silently substituting a different statistical method.

options(
  warn = 1,
  repos = c(CRAN = "https://cloud.r-project.org"),
  Ncpus = max(1L, parallel::detectCores())
)

# Packages whose absence makes the image not worth shipping. Each maps to a
# method the UI offers.
REQUIRED <- c(
  "vegan",      # community ecology helpers
  "DESeq2",     # differential abundance
  "edgeR",      # differential abundance
  "ANCOMBC",    # compositional differential abundance
  "ALDEx2",     # compositional differential abundance
  "mixOmics",   # DIABLO multi-block integration
  "WGCNA"       # co-expression / co-occurrence modules
)

# Nice to have; absence is reported by the API, not fatal to the build.
OPTIONAL <- c(
  "phyloseq",
  "lefser",     # LEfSe
  "maaslin3",   # note: lowercase is the Bioconductor package name
  "pheatmap",
  "ggplot2"
)

message("== Installing BiocManager ==")
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager")
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
  requireNamespace(pkg, quietly = TRUE)
}

message("== Required packages ==")
required_status <- vapply(REQUIRED, install_one, logical(1))

message("== Optional packages ==")
optional_status <- vapply(OPTIONAL, install_one, logical(1))

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
