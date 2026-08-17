#!/usr/bin/env Rscript
# Pin CRAN packages whose current releases are incompatible with this image's
# R (Bioc 3.20 = R 4.4), installed from the CRAN archive:
#
# - gsl: current 2.1-9 needs R >= 4.5; 2.1-8 is the last R>=4.0 release.
#   Needed by energy -> ANCOMBC.
# - CVXR: current 1.9.x dropped the solve() export that ANCOMBC 2.8.x imports
#   at namespace load; 1.0-15 is the last release that exports it.
#
# Kept out of install_r_packages.R and run as its own Docker layer so editing
# this pin list never invalidates the (expensive) core package layer.

options(repos = c(CRAN = "https://cloud.r-project.org"), Ncpus = max(1L, parallel::detectCores()))

pin_from_archive <- function(pkg, url, deps) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    message(sprintf("  already present: %s", pkg))
    return(invisible(TRUE))
  }
  missing_deps <- deps[!vapply(deps, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing_deps)) {
    message(sprintf("  installing %s deps from CRAN: %s", pkg, paste(missing_deps, collapse = ", ")))
    install.packages(missing_deps)
  }
  message(sprintf("  installing pinned %s from CRAN archive", pkg))
  install.packages(url, repos = NULL, type = "source")
  if (!requireNamespace(pkg, quietly = TRUE)) {
    err <- tryCatch({ loadNamespace(pkg); NULL }, error = function(e) conditionMessage(e))
    stop(sprintf("%s pin failed: %s", pkg, if (is.null(err)) "unknown" else err))
  }
}

pin_from_archive(
  "gsl",
  "https://cran.r-project.org/src/contrib/Archive/gsl/gsl_2.1-8.tar.gz",
  deps = c("Rcpp")
)
pin_from_archive(
  "CVXR",
  "https://cran.r-project.org/src/contrib/Archive/CVXR/CVXR_1.0-15.tar.gz",
  deps = c("bit", "bit64", "gmp", "Rmpfr", "ECOSolveR", "scs", "osqp",
           "Rcpp", "RcppEigen", "slam", "methods")
)

# Current CRAN releases in mixOmics' dependency tree need newer low-level
# packages than the base image ships (rlang >= 1.1.7 vs the bundled 1.1.4).
# BiocManager(update = FALSE) never upgrades existing packages, and once an old
# namespace is loaded in an install session the upgrade cannot take effect --
# so upgrade here, before the heavy group loads anything.
LOWLEVEL <- c("rlang", "cli", "glue", "lifecycle", "vctrs", "utf8", "pillar")
message("== Upgrading low-level deps: ", paste(LOWLEVEL, collapse = ", "))
install.packages(LOWLEVEL)

message("Pinned packages installed.")
