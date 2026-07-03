#!/usr/bin/env python3
"""Install R packages via rpy2 with fallback reporting."""
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

R_PACKAGES_STATUS = {}

try:
    import rpy2.robjects as ro
    from rpy2.robjects.packages import importr
    logger.info("rpy2 imported successfully")
    R_PACKAGES_STATUS['rpy2'] = 'available'
except ImportError as e:
    logger.error(f"rpy2 import failed: {e}")
    R_PACKAGES_STATUS['rpy2'] = f'failed: {e}'
    sys.exit(1)

# Install CRAN packages first
cran_packages = ['vegan', 'ggplot2', 'pheatmap']
utils = importr('utils')

for pkg in cran_packages:
    try:
        logger.info(f"Installing CRAN package: {pkg}")
        utils.install_packages(pkg, repos='https://cloud.r-project.org/')
        R_PACKAGES_STATUS[pkg] = 'installed'
        logger.info(f"✓ {pkg} installed successfully")
    except Exception as e:
        R_PACKAGES_STATUS[pkg] = f'failed: {e}'
        logger.error(f"✗ {pkg} installation failed: {e}")

# Install Bioconductor packages via BiocManager
bioc_packages = ['DESeq2', 'edgeR', 'phyloseq']
try:
    logger.info("Installing BiocManager...")
    ro.r('''
    if (!requireNamespace("BiocManager", quietly = TRUE)) {
        install.packages("BiocManager", repos="https://cloud.r-project.org/")
    }
    ''')
    R_PACKAGES_STATUS['BiocManager'] = 'installed'
    logger.info("✓ BiocManager installed")
except Exception as e:
    R_PACKAGES_STATUS['BiocManager'] = f'failed: {e}'
    logger.error(f"BiocManager installation failed: {e}")

for pkg in bioc_packages:
    try:
        logger.info(f"Installing Bioconductor package: {pkg} (this may take several minutes)...")
        ro.r(f'BiocManager::install("{pkg}", update=FALSE, ask=FALSE)')
        R_PACKAGES_STATUS[pkg] = 'installed'
        logger.info(f"✓ {pkg} installed successfully")
    except Exception as e:
        R_PACKAGES_STATUS[pkg] = f'failed: {e}'
        logger.error(f"✗ {pkg} installation failed: {e}")

# Print summary
logger.info("\n" + "="*50)
logger.info("R PACKAGE INSTALLATION SUMMARY")
logger.info("="*50)
for pkg, status in R_PACKAGES_STATUS.items():
    logger.info(f"  {pkg:20s}: {status}")
logger.info("="*50)

# Save results to file
with open('/Users/shihuang/Documents/kimi/workspace/meta2bAnalyst/backend/r_package_status.txt', 'w') as f:
    for pkg, status in R_PACKAGES_STATUS.items():
        f.write(f"{pkg}\t{status}\n")
