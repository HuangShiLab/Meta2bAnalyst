"""
Meta2bAnalyst - Data Parser Service
Handles parsing of TSV/CSV, BIOM, Mothur, 2bRAD, and Strain2bScan formats.
"""
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from scipy import sparse

logger = logging.getLogger(__name__)


class DataParser:
    """Parser for various microbiome data formats."""

    def parse_csv_tsv_chunked(self, file_path: str, sep: str = ',', chunksize: int = 10000) -> pd.DataFrame:
        """Parse CSV/TSV feature table in chunks for large files.

        Uses pd.read_csv with chunksize, then concatenates. Falls back to
        standard parse if file is small enough.

        Args:
            file_path: Path to the CSV/TSV file.
            sep: Separator character.
            chunksize: Number of rows per chunk.

        Returns:
            Concatenated DataFrame.
        """
        # Check file size first
        file_size = os.path.getsize(file_path)
        # Use chunked reading for files > 50MB
        if file_size < 50 * 1024 * 1024:
            return self.parse_csv_tsv(file_path, sep=sep)

        logger.info(f"Large file detected ({file_size / 1024 / 1024:.1f}MB), using chunked reading")

        chunks = []
        try:
            # Read first line to check for #NAME header
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            skiprows = 1 if first_line.startswith('#NAME') else 0

            chunk_iter = pd.read_csv(
                file_path,
                sep=sep,
                index_col=0,
                header=0,
                skiprows=skiprows,
                comment='#',
                engine='python',
                chunksize=chunksize,
                dtype=str,  # Read as string first, then convert
            )

            for chunk in chunk_iter:
                chunk = chunk.apply(pd.to_numeric, errors='coerce')
                chunk = chunk.dropna(how='all', axis=0).dropna(how='all', axis=1)
                chunks.append(chunk)

            df = pd.concat(chunks, axis=0)
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            logger.info(
                f"Parsed chunked CSV/TSV file {file_path}: shape={df.shape}, "
                f"features={len(df.index)}, samples={len(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed chunked parse of CSV/TSV file {file_path}: {e}")
            raise ValueError(f"Failed chunked parse: {e}") from e

    def parse_metaphlan(self, file_path: str) -> pd.DataFrame:
        """Parse MetaPhlAn merged abundance table.

        Expected format:
            - First column: clade_name (taxonomy path like k__Bacteria|p__Firmicutes|...)
            - Subsequent columns: sample relative abundances (0-100)

        Returns:
            DataFrame with taxonomy clades as index and samples as columns.
        """
        try:
            # Read first line to check header
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            df = pd.read_csv(
                file_path,
                sep='	',
                index_col=0,
                header=0,
                engine='python',
            )

            # Rename index to remove leading '#'
            df.index.name = 'clade_name'

            # Convert to numeric
            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)

            logger.info(
                f"Parsed MetaPhlAn file {file_path}: shape={df.shape}, "
                f"clades={len(df.index)}, samples={len(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse MetaPhlAn file {file_path}: {e}")
            raise ValueError(f"Failed to parse MetaPhlAn file: {e}") from e

    def parse_humann3(self, file_path: str) -> pd.DataFrame:
        """Parse HUMAnN3 gene family or pathway abundance table.

        Expected format:
            - First column: feature name (UniRef90_xxx or pathway name)
            - Subsequent columns: sample abundances (RPK or CPM)
            - May contain stratified rows (feature|g__Genus.s__Species)

        Returns:
            DataFrame with features as index and samples as columns.
        """
        try:
            df = pd.read_csv(
                file_path,
                sep='	',
                index_col=0,
                header=0,
                comment='#',
                engine='python',
            )

            # Convert to numeric
            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)

            logger.info(
                f"Parsed HUMAnN3 file {file_path}: shape={df.shape}, "
                f"features={len(df.index)}, samples={len(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse HUMAnN3 file {file_path}: {e}")
            raise ValueError(f"Failed to parse HUMAnN3 file: {e}") from e

    def parse_csv_tsv(self, file_path: str, sep: str = ',') -> pd.DataFrame:
        """Parse CSV/TSV feature table.

        Expected format:
            - First row: sample names (optional #NAME prefix)
            - First column: feature names (OTU/ASV/species/strain)
            - Subsequent columns: abundance values

        Args:
            file_path: Path to the CSV/TSV file.
            sep: Separator character (',' for CSV, '\t' for TSV).

        Returns:
            DataFrame with features as index and samples as columns.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        try:
            # Read first line to check for #NAME header
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            # Check if first line starts with #NAME
            if first_line.startswith('#NAME'):
                # Remove #NAME prefix and treat first line as header row.
                # The format is: #NAME,S01,S02,... — after stripping #NAME we get the sample IDs.
                # We'll rewrite a temporary cleaned file so pandas can parse correctly.
                import tempfile, os as _os
                fd, tmp_path = tempfile.mkstemp(suffix='.csv', text=True)
                try:
                    with _os.fdopen(fd, 'w', encoding='utf-8') as fw:
                        # Write header row (strip #NAME from first line)
                        header_line = first_line.replace('#NAME,', '', 1)
                        if header_line.startswith('#NAME'):
                            header_line = header_line.replace('#NAME', '', 1).lstrip(',')
                        fw.write(header_line + '\n')
                        # Copy remaining lines
                        with open(file_path, 'r', encoding='utf-8') as fr:
                            next(fr)  # skip original first line
                            for line in fr:
                                fw.write(line)
                    df = pd.read_csv(
                        tmp_path,
                        sep=sep,
                        index_col=0,
                        header=0,
                        engine='python',
                    )
                finally:
                    try:
                        _os.unlink(tmp_path)
                    except Exception:
                        pass
            else:
                df = pd.read_csv(
                    file_path,
                    sep=sep,
                    index_col=0,
                    header=0,
                    comment='#',
                    engine='python',
                )

            # Ensure numeric data (exclude index column)
            df = df.apply(pd.to_numeric, errors='coerce')
            # Drop rows/columns that are all NaN
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            logger.info(
                f"Parsed CSV/TSV file {file_path}: shape={df.shape}, "
                f"features={len(df.index)}, samples={len(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse CSV/TSV file {file_path}: {e}")
            raise ValueError(f"Failed to parse CSV/TSV file: {e}") from e

    def parse_biom(self, file_path: str) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
        """Parse BIOM format (BIOM 1.0 / 2.0) with sparse matrix support.

        Args:
            file_path: Path to the BIOM file.

        Returns:
            Tuple of (feature_table DataFrame, optional taxonomy DataFrame).
        """
        try:
            import biom
            table = biom.load_table(file_path)
            
            # Use scipy sparse matrix for memory efficiency
            matrix_data = table.matrix_data
            if sparse.issparse(matrix_data):
                df = pd.DataFrame(
                    matrix_data.toarray().T,
                    index=table.ids(axis='sample'),
                    columns=table.ids(axis='observation'),
                ).T  # Transpose to features x samples
            else:
                df = pd.DataFrame(
                    matrix_data.toarray().T if hasattr(matrix_data, 'toarray') else matrix_data.T,
                    index=table.ids(axis='sample'),
                    columns=table.ids(axis='observation'),
                ).T

            # Extract taxonomy if available
            taxonomy_df = None
            if table.metadata(axis='observation'):
                metadata = table.metadata(axis='observation')
                if metadata and 'taxonomy' in metadata[0]:
                    taxonomy_data = {
                        obs_id: meta['taxonomy']
                        for obs_id, meta in zip(table.ids(axis='observation'), metadata)
                        if meta and 'taxonomy' in meta
                    }
                    if taxonomy_data:
                        taxonomy_df = pd.DataFrame.from_dict(
                            taxonomy_data, orient='index', columns=['taxonomy']
                        )

            logger.info(
                f"Parsed BIOM file {file_path}: shape={df.shape}, "
                f"features={len(df.index)}, samples={len(df.columns)}, sparse={sparse.issparse(matrix_data)}"
            )
            return df, taxonomy_df

        except ImportError:
            logger.warning("biom-format not installed, falling back to JSON parsing")
            return self._parse_biom_json_fallback(file_path)
        except Exception as e:
            logger.error(f"Failed to parse BIOM file {file_path}: {e}")
            raise ValueError(f"Failed to parse BIOM file: {e}") from e

    def _parse_biom_json_fallback(self, file_path: str) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
        """Fallback BIOM 1.0 JSON parser when biom-format is not installed."""
        import json

        with open(file_path, 'r', encoding='utf-8') as f:
            biom_data = json.load(f)

        matrix_type = biom_data.get('matrix_type', 'dense')
        data = biom_data.get('data', [])
        rows = biom_data.get('rows', [])
        columns = biom_data.get('columns', [])

        observation_ids = [r['id'] for r in rows]
        sample_ids = [c['id'] for c in columns]
        n_obs = len(observation_ids)
        n_samp = len(sample_ids)

        if matrix_type == 'dense':
            df = pd.DataFrame(data, index=observation_ids, columns=sample_ids)
        else:  # sparse
            # Use scipy sparse matrix for memory efficiency with large sparse data
            if len(data) > 10000:
                row_indices, col_indices, values = [], [], []
                for row_idx, col_idx, value in data:
                    row_indices.append(row_idx)
                    col_indices.append(col_idx)
                    values.append(value)
                
                sp_matrix = sparse.coo_matrix(
                    (values, (row_indices, col_indices)),
                    shape=(n_obs, n_samp)
                )
                df = pd.DataFrame(
                    sp_matrix.toarray(),
                    index=observation_ids,
                    columns=sample_ids,
                )
            else:
                matrix = [[0] * n_samp for _ in range(n_obs)]
                for row_idx, col_idx, value in data:
                    matrix[row_idx][col_idx] = value
                df = pd.DataFrame(matrix, index=observation_ids, columns=sample_ids)

        # Extract taxonomy from row metadata
        taxonomy_df = None
        taxonomy_data = {}
        for row in rows:
            meta = row.get('metadata', {})
            if meta and 'taxonomy' in meta:
                taxonomy_data[row['id']] = meta['taxonomy']
        if taxonomy_data:
            taxonomy_df = pd.DataFrame.from_dict(
                taxonomy_data, orient='index', columns=['taxonomy']
            )

        logger.info(
            f"Parsed BIOM JSON fallback {file_path}: shape={df.shape}, "
            f"features={len(df.index)}, samples={len(df.columns)}, sparse={matrix_type=='sparse'}"
        )
        return df, taxonomy_df

    def parse_mothur(
        self, shared_path: str, taxonomy_path: Optional[str] = None
    ) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
        """Parse Mothur output (.shared + .taxonomy).

        Args:
            shared_path: Path to the .shared file.
            taxonomy_path: Optional path to the .taxonomy file.

        Returns:
            Tuple of (OTU table DataFrame, optional taxonomy DataFrame).
            The OTU table has OTUs as rows and samples as columns.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        try:
            # Mothur shared format: label\tgroup\tnumOtus\tOTU1\tOTU2...
            df = pd.read_csv(shared_path, sep='\t', index_col=1)
            # Drop label and numOtus columns, keep only OTU columns
            if 'label' in df.columns:
                df = df.drop(columns=['label'])
            if 'numOtus' in df.columns:
                df = df.drop(columns=['numOtus'])

            # Ensure numeric
            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)

            logger.info(
                f"Parsed Mothur shared file {shared_path}: shape={df.shape}, "
                f"OTUs={len(df.index)}, samples={len(df.columns)}"
            )
        except Exception as e:
            logger.error(f"Failed to parse Mothur shared file {shared_path}: {e}")
            raise ValueError(f"Failed to parse Mothur shared file: {e}") from e

        taxonomy_df = None
        if taxonomy_path:
            try:
                # Mothur taxonomy: OTU\ttaxonomy\tsize
                taxonomy_df = pd.read_csv(
                    taxonomy_path,
                    sep='\t',
                    names=['OTU', 'taxonomy', 'size'],
                    index_col=0,
                )
                logger.info(
                    f"Parsed Mothur taxonomy file {taxonomy_path}: "
                    f"entries={len(taxonomy_df)}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to parse Mothur taxonomy file {taxonomy_path}: {e}"
                )
                raise ValueError(f"Failed to parse Mothur taxonomy file: {e}") from e

        return df, taxonomy_df

    def parse_metadata(self, file_path: str) -> pd.DataFrame:
        """Parse metadata table.

        Expected format:
            - First row: sample names (optional #NAME prefix)
            - Subsequent rows: experimental factors (grouping variables)

        Args:
            file_path: Path to the metadata file.

        Returns:
            DataFrame with samples as index and metadata variables as columns.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            if first_line.startswith('#NAME'):
                df = pd.read_csv(
                    file_path,
                    sep='\t',
                    index_col=0,
                    header=0,
                    skiprows=1,
                    comment='#',
                    engine='python',
                )
            else:
                df = pd.read_csv(
                    file_path,
                    sep='\t',
                    index_col=0,
                    header=0,
                    comment='#',
                    engine='python',
                )

            # Try to infer data types
            df = df.infer_objects()

            logger.info(
                f"Parsed metadata file {file_path}: shape={df.shape}, "
                f"samples={len(df.index)}, variables={len(df.columns)}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse metadata file {file_path}: {e}")
            raise ValueError(f"Failed to parse metadata file: {e}") from e

    def parse_metaphlan(self, file_path: str) -> pd.DataFrame:
        """Parse MetaPhlAn merged abundance table.

        Expected format (TSV):
            - Header row: clade_name\tSample1\tSample2\t...
            - Rows: taxonomic clades (e.g. k__Bacteria|p__Firmicutes|...)
            - Values: relative abundances (sum to ~100 per sample)

        Returns:
            DataFrame with clades as index and samples as columns.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            # MetaPhlAn tables sometimes use #SampleID as the first header cell
            if first_line.startswith('#SampleID') or first_line.startswith('#clade_name'):
                df = pd.read_csv(
                    file_path,
                    sep='\t',
                    index_col=0,
                    header=0,
                    engine='python',
                )
            else:
                df = pd.read_csv(
                    file_path,
                    sep='\t',
                    index_col=0,
                    header=0,
                                        engine='python',
                )

            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            logger.info(
                f"Parsed MetaPhlAn file {file_path}: shape={df.shape}, "
                f"clades={len(df.index)}, samples={len(df.columns)}"
            )
            return df
        except Exception as e:
            logger.error(f"Failed to parse MetaPhlAn file {file_path}: {e}")
            raise ValueError(f"Failed to parse MetaPhlAn file: {e}") from e

    def parse_humann3(self, file_path: str) -> pd.DataFrame:
        """Parse HUMAnN3 pathway or gene-family abundance table.

        Expected format (TSV):
            - Header row: # Pathway\tSample1\tSample2\t...  OR
                         # Gene Family\tSample1\tSample2\t...
            - Rows: pathway / gene-family names
            - Values: abundance (RPK, CPM, etc.)

        Returns:
            DataFrame with pathways/gene-families as index and samples as columns.
        """
        try:
            df = pd.read_csv(
                file_path,
                sep='\t',
                index_col=0,
                header=0,
                comment=None,  # HUMAnN3 header starts with '# ' but we want to keep it
                engine='python',
            )
            # The first cell is '# Pathway' or '# Gene Family'; pandas keeps it as index name.
            # Strip leading '# ' from the index name for cleanliness.
            if df.index.name and df.index.name.startswith('# '):
                df.index.name = df.index.name[2:]

            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            logger.info(
                f"Parsed HUMAnN3 file {file_path}: shape={df.shape}, "
                f"features={len(df.index)}, samples={len(df.columns)}"
            )
            return df
        except Exception as e:
            logger.error(f"Failed to parse HUMAnN3 file {file_path}: {e}")
            raise ValueError(f"Failed to parse HUMAnN3 file: {e}") from e

    def parse_2brad_m(
        self,
        species_path: str,
        metadata_path: str,
        functional_path: Optional[str] = None,
    ) -> dict:
        """Parse 2bRAD-M output.

        Args:
            species_path: Path to species abundance table.
            metadata_path: Path to metadata table.
            functional_path: Optional path to functional gene abundance table.

        Returns:
            Dictionary with keys:
                - 'species': species abundance DataFrame
                - 'metadata': metadata DataFrame
                - 'functional': functional gene DataFrame or None

        Raises:
            ValueError: If any file cannot be parsed.
        """
        result = {}

        try:
            result['species'] = self.parse_csv_tsv(species_path, sep='\t')
        except Exception as e:
            logger.error(f"Failed to parse 2bRAD-M species file {species_path}: {e}")
            raise ValueError(f"Failed to parse 2bRAD-M species file: {e}") from e

        try:
            result['metadata'] = self.parse_metadata(metadata_path)
        except Exception as e:
            logger.error(f"Failed to parse 2bRAD-M metadata file {metadata_path}: {e}")
            raise ValueError(f"Failed to parse 2bRAD-M metadata file: {e}") from e

        if functional_path:
            try:
                result['functional'] = self.parse_csv_tsv(functional_path, sep='\t')
            except Exception as e:
                logger.error(
                    f"Failed to parse 2bRAD-M functional file {functional_path}: {e}"
                )
                raise ValueError(f"Failed to parse 2bRAD-M functional file: {e}") from e
        else:
            result['functional'] = None

        logger.info(
            "Parsed 2bRAD-M data: species_shape=%s, metadata_shape=%s, functional=%s",
            result['species'].shape,
            result['metadata'].shape,
            result['functional'] is not None,
        )
        return result

    def parse_strain2bscan(self, file_path: str) -> pd.DataFrame:
        """Parse Strain2bScan output.

        Expected 3D data: sample_id, species, strain, abundance.
        Converts to a long-format DataFrame with columns:
            sample_id, species, strain, abundance.

        Args:
            file_path: Path to the Strain2bScan output file.

        Returns:
            Long-format DataFrame.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        try:
            df = pd.read_csv(file_path, sep='\t')

            # Standardize column names (case-insensitive matching)
            df.columns = [c.lower().strip() for c in df.columns]

            expected_cols = {'sample_id', 'species', 'strain', 'abundance'}
            actual_cols = set(df.columns)

            if not expected_cols.issubset(actual_cols):
                # Try to auto-detect columns if exact names don't match
                col_map = {}
                for exp in expected_cols:
                    for act in actual_cols:
                        if exp in act or act in exp:
                            col_map[exp] = act
                            break
                if len(col_map) >= 3:
                    for exp, act in col_map.items():
                        df[exp] = df[act]
                else:
                    raise ValueError(
                        f"Strain2bScan file missing required columns. "
                        f"Expected {expected_cols}, got {actual_cols}"
                    )

            # Ensure required columns exist
            for col in expected_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")

            # Ensure abundance is numeric
            df['abundance'] = pd.to_numeric(df['abundance'], errors='coerce')
            df = df.dropna(subset=['abundance'])

            # Reorder columns
            df = df[list(expected_cols)]

            logger.info(
                f"Parsed Strain2bScan file {file_path}: entries={len(df)}, "
                f"samples={df['sample_id'].nunique()}, "
                f"species={df['species'].nunique()}, strains={df['strain'].nunique()}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse Strain2bScan file {file_path}: {e}")
            raise ValueError(f"Failed to parse Strain2bScan file: {e}") from e

    def parse_tag2bmap(self, file_path: str) -> pd.DataFrame:
        """Parse Tag2bMap output.

        Contains strain identification results with ANI information.
        Expected columns: sample_id, species, strain, ani, coverage, abundance.

        Args:
            file_path: Path to the Tag2bMap output file.

        Returns:
            DataFrame with strain identification results.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        try:
            df = pd.read_csv(file_path, sep='\t')

            # Standardize column names
            df.columns = [c.lower().strip() for c in df.columns]

            # Map common column name variations
            col_map = {
                'sample_id': ['sample_id', 'sample', 'sampleid', 'sample_name'],
                'species': ['species', 'specie', 'taxon'],
                'strain': ['strain', 'strain_name', 'strain_id'],
                'ani': ['ani', 'ani_value', 'average_nucleotide_identity'],
                'coverage': ['coverage', 'cov', 'genome_coverage'],
                'abundance': ['abundance', 'rel_abundance', 'relative_abundance', 'count'],
            }

            for standard, variants in col_map.items():
                for variant in variants:
                    if variant in df.columns and standard not in df.columns:
                        df[standard] = df[variant]
                        break

            # Ensure numeric columns
            numeric_cols = ['ani', 'coverage', 'abundance']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna(how='all', subset=['sample_id', 'species', 'strain'])

            logger.info(
                f"Parsed Tag2bMap file {file_path}: entries={len(df)}, "
                f"samples={df['sample_id'].nunique()}, "
                f"species={df['species'].nunique()}, strains={df['strain'].nunique()}"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to parse Tag2bMap file {file_path}: {e}")
            raise ValueError(f"Failed to parse Tag2bMap file: {e}") from e

    def to_wide_format(
        self,
        df: pd.DataFrame,
        sample_col: str = 'sample_id',
        feature_col: str = 'feature_id',
        value_col: str = 'abundance',
    ) -> pd.DataFrame:
        """Convert long-format DataFrame to wide format (samples x features).

        Args:
            df: Long-format DataFrame.
            sample_col: Column name for sample IDs.
            feature_col: Column name for feature IDs.
            value_col: Column name for abundance values.

        Returns:
            Wide-format DataFrame with samples as index and features as columns.

        Raises:
            ValueError: If required columns are missing.
        """
        if sample_col not in df.columns:
            raise ValueError(f"Sample column '{sample_col}' not found in DataFrame")
        if feature_col not in df.columns:
            raise ValueError(f"Feature column '{feature_col}' not found in DataFrame")
        if value_col not in df.columns:
            raise ValueError(f"Value column '{value_col}' not found in DataFrame")

        wide_df = df.pivot_table(
            index=sample_col,
            columns=feature_col,
            values=value_col,
            aggfunc='sum',
            fill_value=0,
        )

        logger.info(
            f"Converted long to wide format: shape={wide_df.shape}, "
            f"samples={len(wide_df.index)}, features={len(wide_df.columns)}"
        )
        return wide_df


# ─────────────────────────────── Module-level convenience functions


def detect_file_format(file_path: Path) -> str:
    """Detect file format based on extension and content."""
    ext = file_path.suffix.lower()

    if ext == '.biom':
        return 'biom'
    elif ext in ('.shared',):
        return 'mothur_shared'
    elif ext in ('.taxonomy',):
        return 'mothur_taxonomy'
    elif ext in ('.csv',):
        return 'csv'
    elif ext in ('.tsv', '.txt'):
        # Check if it's a 2bRAD or Strain2bScan file by reading first line
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
        lower_first = first_line.lower()
        if 'strain' in lower_first or 'ani' in lower_first:
            return 'strain'
        if 'tag' in lower_first:
            return 'tag2bmap'
        if lower_first.startswith('#clade_name') or lower_first.startswith('clade_name') or lower_first.startswith('#sampleid\tclade_name'):
            return 'metaphlan'
        if lower_first.startswith('# pathway') or lower_first.startswith('# gene family'):
            return 'humann3'
        if 'k__' in first_line or 'unclassified' in lower_first:
            return 'metaphlan'
        if 'unmapped' in lower_first or 'unintegrated' in lower_first:
            return 'humann3'
        return 'tsv'
    elif ext in ('.h5', '.hdf5'):
        return 'biom_hdf5'
    else:
        return 'unknown'


def parse_tsv_csv(
    file_path: Path, sep: str = '\t', index_col: int = 0, comment: str = '#'
) -> pd.DataFrame:
    """Parse TSV or CSV file into a pandas DataFrame."""
    parser = DataParser()
    return parser.parse_csv_tsv(str(file_path), sep=sep)


def parse_biom_file(file_path: Path) -> pd.DataFrame:
    """Parse BIOM format file into a pandas DataFrame."""
    parser = DataParser()
    df, _ = parser.parse_biom(str(file_path))
    return df


def parse_mothur_shared(file_path: Path) -> pd.DataFrame:
    """Parse Mothur .shared file into a pandas DataFrame."""
    parser = DataParser()
    df, _ = parser.parse_mothur(str(file_path))
    return df


def parse_mothur_taxonomy(file_path: Path) -> pd.DataFrame:
    """Parse Mothur .taxonomy file into a pandas DataFrame."""
    parser = DataParser()
    _, tax_df = parser.parse_mothur('', str(file_path))
    return tax_df


def parse_2brad_file(file_path: Path) -> pd.DataFrame:
    """Parse 2bRAD-M species abundance table."""
    parser = DataParser()
    return parser.parse_csv_tsv(str(file_path), sep='\t')


def parse_strain2bscan(file_path: Path) -> pd.DataFrame:
    """Parse Strain2bScan output file."""
    parser = DataParser()
    return parser.parse_strain2bscan(str(file_path))


def parse_tag2bmap(file_path: Path) -> pd.DataFrame:
    """Parse Tag2bMap output file."""
    parser = DataParser()
    return parser.parse_tag2bmap(str(file_path))


def parse_data_file(
    file_path: Path,
    file_type: Optional[str] = None,
    use_chunks: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """
    Parse a data file and return a pandas DataFrame.

    Args:
        file_path: Path to the data file.
        file_type: Optional explicit file type hint.
        use_chunks: Whether to use chunked reading for large files.

    Returns:
        Tuple of (DataFrame, detected_format).
    """
    detected_format = file_type or detect_file_format(file_path)
    # 'microbiome' / 'metabolome' are semantic upload labels, not parser formats.
    # Auto-detect the actual file format so HUMAnN3 / MetaPhlAn headers are handled.
    if detected_format in ('microbiome', 'metabolome'):
        detected_format = detect_file_format(file_path)
    logger.info(f"Parsing file {file_path} as format: {detected_format}")

    parser = DataParser()

    if detected_format == 'metadata':
        # Metadata files keep categorical variables as-is (do not coerce numeric).
        df = parser.parse_metadata(str(file_path))
    elif detected_format == 'metaphlan':
        df = parser.parse_metaphlan(str(file_path))
    elif detected_format == 'humann3':
        df = parser.parse_humann3(str(file_path))
    elif detected_format in ('tsv', 'txt'):
        if use_chunks:
            df = parser.parse_csv_tsv_chunked(str(file_path), sep='\t')
        else:
            df = parser.parse_csv_tsv(str(file_path), sep='\t')
    elif detected_format == 'csv':
        if use_chunks:
            df = parser.parse_csv_tsv_chunked(str(file_path), sep=',')
        else:
            df = parser.parse_csv_tsv(str(file_path), sep=',')
    elif detected_format == 'biom':
        df, _ = parser.parse_biom(str(file_path))
    elif detected_format == 'mothur_shared':
        df, _ = parser.parse_mothur(str(file_path))
    elif detected_format == 'mothur_taxonomy':
        df = parse_mothur_taxonomy(file_path)
    elif detected_format == 'strain':
        df = parser.parse_strain2bscan(str(file_path))
    elif detected_format == 'tag2bmap':
        df = parser.parse_tag2bmap(str(file_path))
    elif detected_format == '2brad':
        if use_chunks:
            df = parser.parse_csv_tsv_chunked(str(file_path), sep='\t')
        else:
            df = parser.parse_csv_tsv(str(file_path), sep='\t')
    else:
        # Fallback: try as TSV
        logger.warning(f"Unknown format '{detected_format}', attempting TSV parse")
        if use_chunks:
            df = parser.parse_csv_tsv_chunked(str(file_path), sep='\t')
        else:
            df = parser.parse_csv_tsv(str(file_path), sep='\t')

    logger.info(
        f"Parsed {file_path}: shape={df.shape}, features={len(df.index)}, "
        f"samples={len(df.columns)}"
    )
    return df, detected_format


def to_sparse_matrix(df: pd.DataFrame, threshold: float = 0.7) -> sparse.csr_matrix:
    """Convert DataFrame to scipy sparse matrix if sparsity is high enough.

    Args:
        df: Feature table DataFrame.
        threshold: Minimum sparsity ratio (zeros / total) to convert.

    Returns:
        scipy sparse matrix in CSR format.
    """
    sparsity = (df == 0).sum().sum() / df.size
    if sparsity < threshold:
        logger.info(f"Sparsity {sparsity:.2f} below threshold {threshold}, keeping dense")
        return sparse.csr_matrix(df.values)
    
    logger.info(f"Converting to sparse matrix (sparsity={sparsity:.2f})")
    return sparse.csr_matrix(df.values)


def write_intermediate_result(df: pd.DataFrame, path: Path, format: str = 'parquet') -> Path:
    """Write intermediate analysis result to disk to free memory.

    Args:
        df: DataFrame to save.
        path: Output path.
        format: Output format ('parquet', 'csv', 'feather').

    Returns:
        Path to saved file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == 'parquet':
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pandas(df)
        pq.write_table(table, str(path))
    elif format == 'feather':
        df.to_feather(str(path))
    else:
        df.to_csv(str(path), sep='\t')
    
    logger.info(f"Saved intermediate result to {path} ({path.stat().st_size / 1024 / 1024:.1f}MB)")
    return path
